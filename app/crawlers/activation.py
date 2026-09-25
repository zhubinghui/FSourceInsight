"""Human approval of crawl recipes: evidence, CAS on activation_generation and audit (spec §4).

Runs inside the Admin request transaction (db.session). Lock order: source -> state -> profile.
"""
from datetime import timedelta
import hashlib
import json

from sqlalchemy import select

from app.extensions import db
from app.models.crawl_learning import CrawlRepairAttempt
from app.models.crawl_runtime import CrawlSchemaDecision, CrawlSourceState
from app.models.crawl_schema import CrawlPreviewReport, CrawlSchemaVersion, CrawlSourceProfile
from app.models.source import NewsSource
from . import _source_policy, schedule
from ._preview import source_fingerprint
from .schema import validate_recipe

EVIDENCE_AGE = timedelta(hours=24)


class Refused(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def learning_identity(version_id):
    return db.session.scalar(select(CrawlRepairAttempt.session_id).where(
        CrawlRepairAttempt.candidate_id == version_id).limit(1))


def report_is_current(report, source, profile, candidate):
    from .engine import CrawlEngine
    return not (report.status == 'stale' or not source.is_active or report.generation != profile.generation
                or report.source_fingerprint != source_fingerprint(source)
                or report.recipe_hash != candidate.recipe_hash or report.engine_version != CrawlEngine.VERSION
                or not _source_policy.matches_report(_source_policy.latest(profile), source, profile, report.report))


def _usable(report, source, profile, candidate):
    return (report.status == 'ready' and report.report.get('source_policy') is not None
            and report.created_at >= schedule.now() - EVIDENCE_AGE
            and report_is_current(report, source, profile, candidate))


def eligible_reports(source, profile, candidate):
    reports = (CrawlPreviewReport.query.filter_by(version_id=candidate.id, status='ready')
               .order_by(CrawlPreviewReport.id.desc()).limit(20).all())
    return [report for report in reports if _usable(report, source, profile, candidate)]


def rejected(version_id):
    return db.session.scalar(select(CrawlSchemaDecision.id).where(
        CrawlSchemaDecision.version_id == version_id, CrawlSchemaDecision.action == 'reject').limit(1)) is not None


def label(profile, candidate):
    if candidate.id == profile.active_version_id:
        return 'Active'
    if rejected(candidate.id):
        return 'Rejected'
    if candidate.id == profile.previous_version_id:
        return 'Previous'
    return candidate.status.capitalize()


def _locked(source_id, expected):
    source = NewsSource.query.filter_by(id=source_id).populate_existing().with_for_update().first()
    if source is None:
        raise Refused(404, 'Source not found')
    state = CrawlSourceState.query.filter_by(source_id=source_id).populate_existing().with_for_update().first()
    if state is None:
        state = CrawlSourceState(source_id=source_id, next_due_at=schedule.now(), due_reason='activation')
        db.session.add(state)
    profile = CrawlSourceProfile.query.filter_by(source_id=source_id).populate_existing().with_for_update().first()
    if profile is None:
        raise Refused(404, 'No crawl profile for this source')
    if expected != str(profile.activation_generation):
        raise Refused(409, 'Activation changed; reload before deciding')
    return source, state, profile


def _candidate(profile, version_id):
    candidate = db.session.get(CrawlSchemaVersion, version_id)
    if candidate is None or candidate.profile_id != profile.id:
        raise Refused(404, 'Candidate not found')
    return candidate


def _policy(source, profile):
    record = _source_policy.latest(profile)
    if _source_policy.state(record, source, profile) != 'effective':
        raise Refused(409, 'Source policy is not effective')
    return record


def _valid_recipe(candidate):
    try:
        recipe = validate_recipe(candidate.recipe)
    except ValueError:
        raise Refused(409, 'Recipe no longer validates') from None
    if recipe.fingerprint != candidate.recipe_hash:
        raise Refused(409, 'Recipe changed')


def _decide(profile, action, actor_id, *, version_id=None, from_version_id=None, record=None,
            evidence=(None, None, None), reason=None):
    kind, ref, digest = evidence
    db.session.add(CrawlSchemaDecision(
        profile_id=profile.id, action=action, version_id=version_id, from_version_id=from_version_id,
        activation_generation=profile.activation_generation, evidence_kind=kind, evidence_ref=ref,
        evidence_hash=digest, source_generation=profile.source_generation,
        policy_version_id=record.id if record else None, actor_id=actor_id, reason=reason,
        created_at=schedule.now()))


def approve(source_id, version_id, actor_id, expected, report_id=None):
    from . import validation
    source, state, profile = _locked(source_id, expected)
    candidate = _candidate(profile, version_id)
    if not source.is_active:
        raise Refused(409, 'Source is disabled')
    record = _policy(source, profile)
    if candidate.id == profile.active_version_id:
        raise Refused(409, 'Already active')
    if rejected(candidate.id):
        raise Refused(409, 'Rejected candidates cannot be approved')
    _valid_recipe(candidate)
    identity = learning_identity(candidate.id)
    if identity:
        if report_id is not None:
            raise Refused(400, 'Learned candidates are approved on holdout validation')
        view = validation.view(db.session, identity)
        if view is None or view.state != 'passed':
            raise Refused(409, 'Holdout validation has not passed')
        evidence = ('holdout', identity, _digest(view.result))
    else:
        if report_id is None or not report_id.isdigit():
            raise Refused(400, 'Choose a preview report')
        report = db.session.get(CrawlPreviewReport, int(report_id))
        if report is None or report.version_id != candidate.id:
            raise Refused(404, 'Preview report not found')
        if not _usable(report, source, profile, candidate):
            raise Refused(409, 'Preview evidence is not current')
        evidence = ('preview', str(report.id), _digest(report.report))
    previous = profile.active_version_id
    profile.previous_version_id, profile.active_version_id = previous, candidate.id
    profile.active_source_generation = profile.source_generation
    profile.activation_generation += 1
    _decide(profile, 'approve', actor_id, version_id=candidate.id, from_version_id=previous,
            record=record, evidence=evidence)
    state.next_due_at, state.due_reason = schedule.now(), 'activation'
    db.session.commit()


def reject(source_id, version_id, actor_id, expected, reason=''):
    _, _, profile = _locked(source_id, expected)
    candidate = _candidate(profile, version_id)
    if candidate.id == profile.active_version_id:
        raise Refused(409, 'Retire or roll back the active version first')
    if rejected(candidate.id):
        raise Refused(409, 'Already rejected')
    _decide(profile, 'reject', actor_id, version_id=candidate.id, reason=(reason or '').strip()[:200] or None)
    db.session.commit()


def rollback(source_id, actor_id, expected):
    source, state, profile = _locked(source_id, expected)
    target = profile.previous_version_id
    if target is None:
        raise Refused(409, 'No previous version')
    approved = db.session.scalar(select(CrawlSchemaDecision).where(
        CrawlSchemaDecision.profile_id == profile.id, CrawlSchemaDecision.version_id == target,
        CrawlSchemaDecision.action.in_(('approve', 'rollback'))).order_by(CrawlSchemaDecision.id.desc()).limit(1))
    if approved is None or approved.source_generation != profile.source_generation:
        raise Refused(409, 'The source changed since that version was approved; approve it again')
    if not source.is_active:
        raise Refused(409, 'Source is disabled')
    record = _policy(source, profile)
    _valid_recipe(db.session.get(CrawlSchemaVersion, target))
    current = profile.active_version_id
    profile.active_version_id, profile.previous_version_id = target, current
    profile.active_source_generation = profile.source_generation
    profile.activation_generation += 1
    _decide(profile, 'rollback', actor_id, version_id=target, from_version_id=current, record=record)
    state.next_due_at, state.due_reason = schedule.now(), 'activation'
    db.session.commit()


def retire(source_id, actor_id, expected):
    _, _, profile = _locked(source_id, expected)
    current = profile.active_version_id
    if current is None:
        raise Refused(409, 'Already using the legacy crawler')
    profile.previous_version_id, profile.active_version_id = current, None
    profile.active_source_generation = None
    profile.activation_generation += 1
    _decide(profile, 'retire', actor_id, from_version_id=current)
    db.session.commit()
