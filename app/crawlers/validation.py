"""Frozen-candidate holdouts within controlled learning; no network or model tools."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
import uuid

from flask import current_app
from sqlalchemy import select

from app.llm import budget
from app.models import (NewsSource, CrawlSourceProfile, CrawlPolicyVersion, CrawlSchemaVersion,
                        CrawlCaptureManifest, CrawlPreviewReport, CrawlRepairSession, CrawlRepairAttempt,
                        CrawlValidationReport, CrawlLearningHistory)
from . import _capture, _evidence, _learning_history, _source_policy
from ._preview import source_fingerprint
from .engine import CrawlEngine
from .schema import validate_recipe

VERSION = 'holdout-validation.v1'
_TERMINAL = {'passed', 'failed', 'inconclusive'}


def freeze(session, learning, candidate, doc):
    base = session.get(CrawlSchemaVersion, learning.base_version_id)
    profile = session.get(CrawlSourceProfile, base.profile_id)
    policy = session.get(CrawlPolicyVersion, doc['source_policy']['id'])
    binding = {'format': VERSION, 'session_id': learning.id, 'input_hash': learning.input_hash,
        'source_policy_inputs': {'fetch_policy': policy.document['fetch_policy'],
                                'quality_profile': policy.document['quality_profile']},
        'candidate_id': candidate.id, 'recipe_hash': candidate.recipe_hash, 'base_id': base.id,
        'base_hash': base.recipe_hash, 'profile_id': profile.id, 'source_id': learning.source_id,
        'cutoff': profile.capture_generation, 'generation': profile.generation,
        'source_generation': profile.source_generation, 'source_fingerprint': doc['source_fingerprint'],
        'source_policy': doc['source_policy'], 'engine_version': CrawlEngine.VERSION}
    session.add(CrawlValidationReport(id=str(uuid.uuid4()), session_id=learning.id, candidate_id=candidate.id,
        binding=binding, binding_hash=_capture.fingerprint(binding), state='awaiting_evidence', created_at=budget.now()))


def _reports(session):
    """v3 candidates enroll atomically; legacy candidates never acquire a fake freeze."""
    expected = set(session.execute(select(CrawlRepairAttempt.session_id, CrawlRepairAttempt.candidate_id)
        .join(CrawlRepairSession).where(CrawlRepairSession.protocol_version == 'crawl-learning.v3',
                                       CrawlRepairAttempt.candidate_id.is_not(None))).all())
    rows = session.scalars(select(CrawlValidationReport).limit(_learning_history.MAX_RECORDS + 1)).all()
    if len(rows) > _learning_history.MAX_RECORDS or {(r.session_id, r.candidate_id) for r in rows} != expected:
        raise ValueError('Validation history unavailable')
    marker = session.get(CrawlLearningHistory, 1)
    selections = [r.selection.get('sequence') for r in rows if isinstance(r.selection, dict)]
    if (marker is None or type(marker.selection_generation) is not int
            or not 0 <= marker.selection_generation <= _learning_history.MAX_RECORDS
            or len(selections) != marker.selection_generation
            or any(type(n) is not int for n in selections)
            or sorted(selections) != list(range(1, marker.selection_generation + 1))):
        raise ValueError('Selection history unavailable')
    for row in rows:
        if (not isinstance(row.binding, dict) or row.binding.get('format') != VERSION
                or row.binding.get('session_id') != row.session_id or row.binding.get('candidate_id') != row.candidate_id
                or _capture.fingerprint(row.binding) != row.binding_hash
                or row.state not in _TERMINAL | {'awaiting_evidence', 'running'}):
            raise ValueError('Validation history unavailable')
        if row.selection is not None:
            if (not isinstance(row.selection, dict) or _capture.fingerprint(row.selection) != row.selection_hash
                    or row.selection.get('actor_id') != row.requested_by_id or row.requested_by_id is None
                    or row.deadline_at is None
                    or row.selection.get('deadline_at') != row.deadline_at.replace(microsecond=0).isoformat()):
                raise ValueError('Selection history unavailable')
            documents = row.selection.get('fingerprints')
            if documents is not None and _learning_history.display_documents(SimpleNamespace(exposure=documents)) is None:
                raise ValueError('Selection history unavailable')
        if row.state in _TERMINAL:
            if (not isinstance(row.result, dict) or row.result.get('status') != row.state
                    or set(row.result) != {'status', 'reason', 'lists', 'details', 'templates', 'engine_status', 'errors'}
                    or _capture.fingerprint({'binding': row.binding_hash, 'selection': row.selection_hash,
                                             'result': row.result}) != row.result_hash):
                raise ValueError('Validation result unavailable')
        elif row.result is not None or row.result_hash is not None:
            raise ValueError('Validation state unavailable')
    return rows


def require_history(session):
    _reports(session)


def _authority(session, row):
    from .learning import enabled
    enabled()
    _learning_history.require(session)
    b = row.binding
    if not isinstance(b, dict) or _capture.fingerprint(b) != row.binding_hash or b.get('format') != VERSION:
        raise ValueError('Validation binding unavailable')
    learning = session.get(CrawlRepairSession, row.session_id)
    source = session.scalar(select(NewsSource).where(NewsSource.id == b['source_id'])
                            .with_for_update().execution_options(populate_existing=True))
    profile = session.scalar(select(CrawlSourceProfile).where(CrawlSourceProfile.id == b['profile_id'])
                             .with_for_update().execution_options(populate_existing=True))
    policy = session.scalar(select(CrawlPolicyVersion).where(CrawlPolicyVersion.profile_id == b['profile_id'])
                            .order_by(CrawlPolicyVersion.generation.desc()).limit(1)
                            .with_for_update().execution_options(populate_existing=True))
    base = session.get(CrawlSchemaVersion, b['base_id'])
    candidate = session.get(CrawlSchemaVersion, row.candidate_id)
    if (not learning or not source or not profile or not base or not candidate
            or b['session_id'] != row.session_id or learning.source_id != source.id
            or learning.input_hash != b['input_hash'] or learning.base_version_id != base.id
            or learning.state != 'awaiting_validation' or profile.source_id != source.id
            or base.profile_id != profile.id or candidate.profile_id != profile.id
            or b['candidate_id'] != candidate.id or b['base_hash'] != base.recipe_hash
            or b['recipe_hash'] != candidate.recipe_hash or b['engine_version'] != CrawlEngine.VERSION
            or validate_recipe(base.recipe).fingerprint != base.recipe_hash
            or validate_recipe(candidate.recipe).fingerprint != candidate.recipe_hash
            or source_fingerprint(source) != b['source_fingerprint']
            or profile.generation != b['generation'] or profile.source_generation != b['source_generation']
            or type(b['cutoff']) is not int or not 0 <= b['cutoff'] <= profile.capture_generation
            or _capture.history_state(profile, session) != 'tracked'
            or _source_policy.state(policy, source, profile) != 'effective'
            or b['source_policy'] != {'id': policy.id, 'hash': policy.document_hash}):
        raise ValueError('Validation inputs changed')
    fetch_policy, quality = _source_policy.inputs(policy)
    return base, candidate, fetch_policy, quality


def _first(session, row):
    b = row.binding
    return session.scalar(select(CrawlCaptureManifest).where(CrawlCaptureManifest.profile_id == b['profile_id'],
        CrawlCaptureManifest.version_id == b['base_id'], CrawlCaptureManifest.sequence > b['cutoff'])
        .order_by(CrawlCaptureManifest.sequence).limit(1))


def _samples(session, row, fetch_policy, quality):
    b, selection = row.binding, row.selection
    capture = _first(session, row)
    if (not capture or capture.id != row.capture_id or not isinstance(selection, dict)
            or _capture.fingerprint(selection) != row.selection_hash
            or selection['capture_hash'] != capture.document_hash):
        raise ValueError('Selection unavailable')
    doc = _capture.checked_document(capture, b['source_id'])
    if (doc['generation'] != b['generation'] or doc['source_generation'] != b['source_generation']
            or doc['source_fingerprint'] != b['source_fingerprint'] or doc['source_policy'] != b['source_policy']
            or doc['recipe_hash'] != b['base_hash'] or doc['engine_version'] != b['engine_version']
            or doc['fetch_policy_hash'] != _capture.fingerprint(b['source_policy_inputs']['fetch_policy'])
            or doc['quality_profile_hash'] != _capture.fingerprint(b['source_policy_inputs']['quality_profile'])):
        raise ValueError('Selection inputs changed')
    binding = _evidence.binding(b['source_id'], b['base_id'], b['generation'], b['source_fingerprint'],
        b['base_hash'], CrawlEngine.VERSION, fetch_policy, quality, doc['capture_id'])
    pages = _evidence.load(current_app.config.get('CRAWL_EVIDENCE_DIR'), selection['evidence'], binding)
    fingerprints = _learning_history.documents(pages)
    observed = [{k: v for k, v in p.items() if k not in ('text_hash', 'text_version')} for p in fingerprints]
    if observed != doc['documents'] or selection.get('fingerprints', fingerprints) != fingerprints:
        raise ValueError('Selection document mismatch')
    return pages, fingerprints


def _tainted(session, row, fingerprints, base):
    seen = [page for attempt in session.scalars(select(CrawlRepairAttempt)) for page in attempt.exposure]
    for prior in _reports(session):
        if prior.selection and prior.selection['sequence'] < row.selection['sequence']:
            seen.extend(prior.selection.get('fingerprints', []))
    raw = {p['snapshot_id'] for p in seen}
    text = {p['text_hash'] for p in seen}
    urls = {p[key] for p in seen for key in ('requested_url_hash', 'document_url_hash')}
    lists = {hashlib.sha256(p['url'].encode()).hexdigest() for p in base.get('list_pages', [])}
    details = [p for p in fingerprints if p['requested_url_hash'] not in lists]
    return (any(p['snapshot_id'] in raw or p['text_hash'] in text for p in fingerprints)
            or any(p['requested_url_hash'] in urls or p['document_url_hash'] in urls for p in details)
            or len({p['text_hash'] for p in details}) != len(details)
            or len({p['document_url_hash'] for p in details}) != len(details))


def _result(status, reason, *, details=0, templates=(), engine_status=None, errors=()):
    return {'status': status, 'reason': reason, 'lists': 1 if details else 0, 'details': details,
            'templates': list(templates), 'engine_status': engine_status, 'errors': list(errors)[:20]}


def _evaluate(work):
    base, candidate = work.base, work.candidate
    if any(recipe.get('extractor') != 'html' or len(recipe['list_pages']) != 1
           or recipe['list_pages'][0].get('pagination') for recipe in (base, candidate)):
        return _result('inconclusive', 'unsupported_sampling_inventory')
    deadline = time.monotonic() + 20
    def run(recipe):
        left = min(work.fetch_policy.max_seconds, deadline - time.monotonic())
        if left <= 0:
            raise ValueError('Validation deadline')
        return CrawlEngine(work.source_id, recipe=recipe, snapshots=work.pages,
            fetch_policy=replace(work.fetch_policy, max_seconds=left), profile=work.quality).preview()
    inventory = run({**base, 'detail_templates': []})
    expected = {a.url for a in inventory.articles}
    pages = {p.url: p for p in work.pages}
    if inventory.status != 'ready' or len(expected) < 3 or not expected <= pages.keys():
        return _result('inconclusive', 'insufficient_independent_details')
    result = run(candidate)
    covered = set()
    for article in result.articles:
        templates = [(i, t) for i, t in enumerate(candidate.get('detail_templates', []))
            if urlsplit(article.url).hostname == t['match']['host']
            and urlsplit(article.url).path.startswith(t['match']['path_prefix'])]
        if not templates or article.content_level != 'full' or article.url not in pages:
            return _result('failed', 'detail_quality_failed', engine_status=result.status)
        index, template = max(templates, key=lambda pair: len(pair[1]['match']['path_prefix']))
        evidence = next((p for p in article.provenance if p.field == 'content'), None)
        if (not evidence or evidence.snapshot_id != pages[article.url].response.observation.snapshot_id
                or not evidence.locator.endswith(f':detail:{index}:content')):
            return _result('failed', 'detail_provenance_failed', engine_status=result.status)
        covered.add(index)
    if result.status != 'ready' or {a.url for a in result.articles} != expected:
        return _result('failed', 'inventory_or_template_coverage_failed', engine_status=result.status,
                       errors=[e.code for e in result.errors])
    if covered != set(range(len(candidate.get('detail_templates', [])))):
        return _result('inconclusive', 'insufficient_template_coverage', engine_status=result.status)
    return _result('passed', 'controlled_holdout_checks_passed', details=len(expected),
                   templates=sorted(covered), engine_status=result.status)


def _save(row, result):
    row.state, row.result = result['status'], result
    row.result_hash = _capture.fingerprint({'binding': row.binding_hash, 'selection': row.selection_hash, 'result': result})


def run(source_id, identity, actor_id):
    with budget.transaction() as session:
        row = session.scalar(select(CrawlValidationReport).where(CrawlValidationReport.session_id == identity))
        learning = session.get(CrawlRepairSession, identity)
        if not row or not learning or learning.source_id != source_id:
            raise LookupError
        base, candidate, fetch_policy, quality = _authority(session, row)
        if row.state != 'awaiting_evidence':
            return
        capture = _first(session, row)
        if capture is None:
            raise ValueError('New base evidence required')
        report = session.get(CrawlPreviewReport, capture.preview_report_id)
        row.capture_id = capture.id
        marker = session.get(CrawlLearningHistory, 1)
        marker.selection_generation += 1
        row.state, row.requested_by_id = 'running', actor_id
        row.deadline_at = budget.now().replace(microsecond=0) + timedelta(seconds=30)
        row.selection = {'sequence': marker.selection_generation, 'capture_hash': capture.document_hash,
                         'actor_id': actor_id, 'deadline_at': row.deadline_at.replace(microsecond=0).isoformat(),
                         'evidence': report.report.get('evidence') if report else None}
        row.selection_hash = _capture.fingerprint(row.selection)
        try:
            pages, fingerprints = _samples(session, row, fetch_policy, quality)
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            _save(row, _result('inconclusive', 'selected_evidence_unavailable'))
            return
        row.selection = {**row.selection, 'fingerprints': fingerprints}
        row.selection_hash = _capture.fingerprint(row.selection)
        if _tainted(session, row, fingerprints, base.recipe):
            _save(row, _result('inconclusive', 'previously_seen_evidence'))
            return
        work = SimpleNamespace(base=base.recipe, candidate=candidate.recipe, pages=pages, source_id=source_id,
                               fetch_policy=fetch_policy, quality=quality, fingerprints=fingerprints)
        row_id = row.id
    try:
        result = _evaluate(work)
    except Exception:
        result = _result('inconclusive', 'execution_unavailable')
    with budget.transaction() as session:
        row = session.get(CrawlValidationReport, row_id)
        if row is None or row.state != 'running':
            return
        try:
            _authority(session, row)
            _, final_fingerprints = _samples(session, row, fetch_policy, quality)
            if _tainted(session, row, final_fingerprints, work.base):
                raise ValueError('Evidence was exposed')
            if budget.now() >= row.deadline_at:
                raise ValueError('Validation deadline')
        except (ValueError, TypeError, KeyError, OSError, RecursionError):
            result = _result('inconclusive', 'inputs_changed_or_deadline')
        _save(row, result)


def expire(session):
    rows = session.scalars(select(CrawlValidationReport).where(CrawlValidationReport.state == 'running',
        CrawlValidationReport.deadline_at <= budget.now()).order_by(CrawlValidationReport.deadline_at).limit(50))
    for row in rows:
        _save(row, _result('inconclusive', 'execution_expired'))


def view(session, identity):
    row = session.scalar(select(CrawlValidationReport).where(CrawlValidationReport.session_id == identity))
    if row is None:
        return None
    state, result = row.state, row.result
    try:
        _authority(session, row)
        if state in _TERMINAL:
            if _capture.fingerprint({'binding': row.binding_hash, 'selection': row.selection_hash, 'result': result}) != row.result_hash:
                raise ValueError('Report unavailable')
            if state == 'passed':
                base, _, policy, quality = _authority(session, row)
                _, fingerprints = _samples(session, row, policy, quality)
                if _tainted(session, row, fingerprints, base.recipe):
                    raise ValueError('Evidence was exposed')
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        state, result = 'stale', None
    return SimpleNamespace(state=state, recorded_state=row.state, result=result)
