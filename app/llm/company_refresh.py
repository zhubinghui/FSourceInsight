"""Coalesced refresh of an existing company analysis; no paid takeover.

At most one queued/running job per company. The company generation is pinned
at claim and re-checked before every paid attempt and before the result is
applied, so a concurrent edit is never overwritten. Transitions use the
accounting mutex; no fetch or model call happens inside a transaction.
"""
import hashlib
import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Article, ArticleCompany, Company, CompanyRefreshJob, LLMConfig, LLMReservation
from app.llm import budget

PROTOCOL = 'company-refresh.v1'
TASK = 'app.llm.refresh_tasks.refresh'
FIELDS = ('name', 'sector', 'headquarters', 'description', 'spinoff_origin', 'company_stage')
logger = logging.getLogger(__name__)


def digest(messages):
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def _row(session, model, identity):
    return session.scalar(select(model).where(model.id == identity).with_for_update()
                          .execution_options(populate_existing=True))


def _close(item, state, reason):
    item.state, item.reason = state, reason
    item.finished_at, item.active_company_id = budget.now().replace(microsecond=0), None


def request(company_id, trigger, trigger_ref=None):
    """Return (job id, created). An active job absorbs further requests."""
    with budget.transaction() as session:
        company = _row(session, Company, company_id)
        if company is None:
            return None, False
        active = session.scalar(select(CompanyRefreshJob.id).where(
            CompanyRefreshJob.active_company_id == company_id))
        if active:
            return active, False
        timestamp = budget.now().replace(microsecond=0)
        item = CompanyRefreshJob(
            id=str(uuid.uuid4()), company_id=company_id, active_company_id=company_id,
            trigger=trigger, trigger_ref=(trigger_ref or '')[:80] or None, protocol=PROTOCOL,
            state='queued', created_at=timestamp, next_dispatch_at=timestamp,
            expires_at=timestamp + timedelta(hours=24))
        session.add(item)
        identity = item.id
    return identity, True


def publish(identity):
    from celery_app import celery
    try:
        with budget.transaction() as session:
            item = _row(session, CompanyRefreshJob, identity)
            if item is None or item.state != 'queued' or budget.now() < item.next_dispatch_at:
                return
            if budget.now() >= item.expires_at:
                _close(item, 'blocked', 'queue_expired')
                return
            # Whole seconds rounded up keep at least 120s between dispatches.
            item.next_dispatch_at = budget.now().replace(microsecond=0) + timedelta(seconds=121)
        celery.send_task(TASK, args=[identity], queue='llm')
    except Exception:
        logger.warning('Company refresh dispatch unavailable; durable intent retained')


def claim(identity, claim_id):
    """Pin inputs and generation; return prompt arguments and homepage URL."""
    with budget.transaction() as session:
        item = _row(session, CompanyRefreshJob, identity)
        if item is None or item.state != 'queued':
            return None
        if budget.now() >= item.expires_at:
            _close(item, 'blocked', 'queue_expired')
            return None
        company = _row(session, Company, item.company_id) if item.company_id else None
        if company is None or item.protocol != PROTOCOL:
            _close(item, 'stale', 'company_unavailable')
            return None
        paid = session.scalar(select(LLMReservation.id).where(
            LLMReservation.company_refresh_id == identity).limit(1))
        if item.claim_id is not None or paid:
            # A reverted queued state is never permission to repeat a call.
            _close(item, 'blocked', 'prior_execution')
            return None
        recent = session.scalars(select(Article).join(ArticleCompany).where(
            ArticleCompany.company_id == company.id).order_by(Article.published_at.desc()).limit(5)).all()
        analysis = company.ai_analysis if isinstance(company.ai_analysis, dict) else {}
        site = (analysis.get('website') or '').strip() if isinstance(analysis.get('website'), str) else ''
        result = {
            'arguments': dict({key: getattr(company, key) for key in FIELDS}, recent_news='\n'.join(
                f'- {a.title_fr or a.title_en or ""}' for a in recent)),
            'site_url': site or company.website or None,
        }
        item.claim_id, item.state = claim_id, 'running'
        item.company_generation = company.analysis_generation
        item.deadline_at = min(item.expires_at, budget.now().replace(microsecond=0) + timedelta(seconds=180))
    return result


def prepare(identity, claim_id, messages):
    """Bind the exact effective prompt after the unlocked homepage fetch."""
    with budget.transaction() as session:
        item = _row(session, CompanyRefreshJob, identity)
        if (item is None or item.state != 'running' or item.claim_id != claim_id
                or item.prompt_hash is not None):
            raise budget.BudgetError('Current company refresh claim required')
        item.prompt_hash = digest(messages)


def _calling(session, identity, messages):
    item = _row(session, CompanyRefreshJob, identity)
    if (item is None or item.state != 'running' or not item.claim_id or item.deadline_at is None
            or item.prompt_hash != digest(messages) or budget.now() >= item.deadline_at):
        raise budget.BudgetError('Persisted current company refresh required')
    company = _row(session, Company, item.company_id) if item.company_id else None
    if company is None or company.analysis_generation != item.company_generation:
        raise budget.BudgetError('Company changed during refresh')
    if budget.now() >= item.deadline_at:
        raise budget.BudgetError('Company refresh expired')
    return item


def check(identity, messages):
    with budget.transaction() as session:
        _calling(session, identity, messages)


def admit(session, identity, messages, config):
    item = _calling(session, identity, messages)
    attempts = session.scalars(select(LLMReservation).where(LLMReservation.company_refresh_id == identity)).all()
    if (len(attempts) >= 3 or any(row.config_id == config.id for row in attempts)
            or any(row.state != 'settled' for row in attempts)):
        raise budget.BudgetError('Company refresh provider attempt unavailable')
    current = _row(session, LLMConfig, config.id)
    keys = ('provider', 'model', 'api_base_url', 'api_key_env_var', 'is_active', 'is_default',
            'tasks', 'role', 'priority', 'max_tokens', 'temperature', 'billing_input_limit',
            'billing_output_limit', 'cost_per_1k_input', 'cost_per_1k_output')
    if current is None or not current.is_active or any(getattr(current, k) != getattr(config, k) for k in keys):
        raise budget.BudgetError('Company refresh model configuration changed')
    if budget.now() >= item.deadline_at:  # Lock reads above may have blocked.
        raise budget.BudgetError('Company refresh expired')


REVISIONS = {
    'ok': ('ai-refresh-website', 'Crawled {site}'),
    'too_thin': ('ai-refresh-news', '{site} returned too little text (likely SPA)'),
    'http_error': ('ai-refresh-news', '{site} returned non-2xx'),
    'fetch_error': ('ai-refresh-news', '{site} unreachable'),
    'no_url': ('ai-refresh-news', 'No website URL on record'),
}


def finish(identity, claim_id, analysis, fetch_status, site_url):
    from app.llm.startup_analysis import website
    from app.llm.tasks import _save_revision
    with budget.transaction() as session:
        item = _row(session, CompanyRefreshJob, identity)
        if item is None or item.state != 'running' or item.claim_id != claim_id:
            return
        company = _row(session, Company, item.company_id) if item.company_id else None
        if budget.now() >= item.deadline_at:
            _close(item, 'blocked', 'execution_expired')
            return
        if company is None or company.analysis_generation != item.company_generation:
            _close(item, 'stale', 'company_changed')
            return
        old = company.ai_analysis if isinstance(company.ai_analysis, dict) else {}
        merged = dict(old)
        for key, value in analysis.items():
            if key == 'competitors':
                if isinstance(value, list) and value:
                    merged['competitors'] = value
            elif key == 'website':
                # The stored website is the next refresh's fetch target.
                if value and website(value):
                    merged['website'] = value
            elif value not in (None, '', []):
                merged[key] = value
        source, trigger = REVISIONS.get(fetch_status, REVISIONS['fetch_error'])
        _save_revision(company, new_data=merged, source=source, trigger=trigger.format(site=site_url))
        company.ai_analysis, company.ai_analysis_at = merged, budget.now().replace(microsecond=0)
        _close(item, 'succeeded', 'analysis_saved')


def fail(identity, claim_id, reason='execution_unavailable'):
    with budget.transaction() as session:
        item = _row(session, CompanyRefreshJob, identity)
        # Ownership also fences exception handling after commit ACK loss.
        if item is None or item.state != 'running' or item.claim_id != claim_id:
            return
        _close(item, 'blocked', reason)


def latest(company_id):
    """Active job first, then the most recently finished one."""
    return db.session.scalar(select(CompanyRefreshJob).where(CompanyRefreshJob.company_id == company_id)
                             .order_by(CompanyRefreshJob.active_company_id.is_(None),
                                       CompanyRefreshJob.created_at.desc(),
                                       CompanyRefreshJob.finished_at.desc()).limit(1))


def recover():
    with Session(db.engine) as session:
        ids = list(session.scalars(select(CompanyRefreshJob.id).where(or_(
            and_(CompanyRefreshJob.state == 'queued', CompanyRefreshJob.next_dispatch_at <= budget.now()),
            and_(CompanyRefreshJob.state == 'running', or_(CompanyRefreshJob.deadline_at <= budget.now(),
                                                           CompanyRefreshJob.deadline_at.is_(None))))
        ).order_by(CompanyRefreshJob.next_dispatch_at, CompanyRefreshJob.id).limit(50)))
    for identity in ids:
        dispatch = False
        with budget.transaction() as session:
            item = _row(session, CompanyRefreshJob, identity)
            if item is None or item.state not in ('queued', 'running'):
                continue
            timestamp = budget.now()
            if timestamp >= item.expires_at or (item.state == 'running' and (
                    item.deadline_at is None or timestamp >= item.deadline_at)):
                _close(item, 'blocked', 'execution_expired')
            elif item.state == 'queued':
                dispatch = True
        if dispatch:
            publish(identity)
