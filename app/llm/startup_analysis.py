"""Source-owned initial company analysis, durable dispatch and no paid takeover.

All transitions use the accounting mutex. No fetch/model invocation occurs in
these transactions. Hashes detect inconsistent records, not DB-owner forgery.
"""
import hashlib
import json
import logging
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Company, StartupAnalysisJob, LLMConfig, LLMReservation
from app.models.startup_source import StartupSource
from app.llm import budget, prompts
from app.llm.contracts import CONTRACT_VERSION
from app.crawlers._fetch_policy import hostname, Rejected

PROTOCOL = 'startup-analysis.v1'
logger = logging.getLogger(__name__)
FIELDS = ('name', 'sector', 'headquarters', 'description', 'spinoff_origin', 'company_stage')
COMPANY_FIELDS = FIELDS + ('slug', 'aliases', 'website', 'is_grenoble', 'is_auto_created',
                           'ai_analysis', 'ai_analysis_at', 'ai_revision_history')


def digest(data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False,
                     separators=(',', ':')).encode()
    if len(raw) > 16384:
        raise budget.BudgetError('Discovery input unavailable')
    return hashlib.sha256(raw).hexdigest()


def source_input(source):
    return {'id': source.id, 'generation': source.analysis_generation,
            'created_at': source.created_at.isoformat(), 'type': source.source_type,
            'url_hash': hashlib.sha256(source.url.encode()).hexdigest(), 'active': source.is_active}


def company_input(company):
    values = {key: getattr(company, key) for key in COMPANY_FIELDS}
    values['ai_analysis_at'] = company.ai_analysis_at.isoformat() if company.ai_analysis_at else None
    return dict(values, id=company.id, generation=company.analysis_generation,
                created_at=company.created_at.isoformat())


def arguments(inputs):
    # Only these bounded metadata fields, never directory pages/homepage fetches.
    return {key: inputs['company'][key] for key in FIELDS}


def messages(inputs):
    return prompts.get_company_analysis_messages(**arguments(inputs), recent_news=None)


def binding(job):
    return digest({'id': job.id, 'protocol': job.protocol, 'inputs': job.inputs,
                   'prompt_hash': job.prompt_hash, 'created_at': job.created_at.isoformat(),
                   'expires_at': job.expires_at.isoformat()})


def label(item):
    """Bounded historical display only; never an execution authorization."""
    try:
        value = item.inputs['company']['name']
        if binding(item) == item.input_hash and isinstance(value, str) and len(value) <= 300:
            return value
    except (budget.BudgetError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return 'Input unavailable'


def website(value):
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if (len(value) > 500 or parsed.scheme not in {'https', 'http'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or any(c.isspace() or ord(c) < 32 or c == '\\' for c in value)):
            return None
        hostname(parsed.hostname)
        if parsed.port not in (None, 80, 443):
            return None
        return value
    except (ValueError, TypeError, Rejected):
        return None


def create(session, source, company):
    """Caller must insert a NEW Company in this same transaction, not backfill."""
    session.flush()
    session.refresh(company)  # Bind DB timestamp precision, not pre-flush values.
    timestamp = budget.now().replace(microsecond=0)
    item = StartupAnalysisJob(
        id=str(uuid.uuid4()), company_id=company.id, source_id=source.id,
        protocol=PROTOCOL, inputs={'source': source_input(source), 'company': company_input(company),
                                  'prompt_version': prompts.PROMPT_VERSION, 'contract_version': CONTRACT_VERSION},
        state='queued', created_at=timestamp, next_dispatch_at=timestamp,
        expires_at=timestamp + timedelta(hours=24))
    item.prompt_hash = digest(messages(item.inputs))
    item.input_hash = binding(item)
    session.add(item)
    return item.id


def publish(identity):
    from celery_app import celery
    try:
        with budget.transaction() as session:
            item = _row(session, StartupAnalysisJob, identity)
            if item is None or item.state != 'queued' or budget.now() < item.next_dispatch_at:
                return
            if budget.now() >= item.expires_at:
                _close(item, 'blocked', 'queue_expired')
                return
            _current(session, item)
            # Conservatively round up: database DATETIME precision must not
            # shorten the minimum 120-second redispatch interval.
            item.next_dispatch_at = budget.now().replace(microsecond=0) + timedelta(seconds=121)
        celery.send_task('app.llm.startup_tasks.analyze', args=[identity], queue='llm')
    except Exception:
        logger.warning('Startup analysis dispatch unavailable; durable intent retained')


def _row(session, model, identity):
    return session.scalar(select(model).where(model.id == identity).with_for_update()
                          .execution_options(populate_existing=True))


def _current(session, item):
    if (item.protocol != PROTOCOL or item.input_hash != binding(item)
            or item.inputs.get('prompt_version') != prompts.PROMPT_VERSION
            or item.inputs.get('contract_version') != CONTRACT_VERSION
            or item.prompt_hash != digest(messages(item.inputs))):
        raise budget.BudgetError('Discovery binding unavailable')
    source = _row(session, StartupSource, item.source_id)
    company = _row(session, Company, item.company_id)
    if (source is None or company is None or not source.is_active
            or company.ai_analysis is not None or not company.is_auto_created
            or source_input(source) != item.inputs['source']
            or company_input(company) != item.inputs['company']):
        raise budget.BudgetError('Discovery inputs changed')
    return company


def _close(item, state, reason):
    item.state, item.reason, item.finished_at = state, reason, budget.now().replace(microsecond=0)


def claim(identity, claim_id):
    with budget.transaction() as session:
        item = _row(session, StartupAnalysisJob, identity)
        if item is None or item.state != 'queued':
            return None
        if budget.now() >= item.expires_at:
            _close(item, 'blocked', 'queue_expired')
            return None
        try:
            _current(session, item)
        except (budget.BudgetError, ValueError, TypeError, KeyError, AttributeError):
            _close(item, 'stale', 'inputs_unavailable')
            return None
        # A reverted queued state is never permission to repeat an old call.
        paid = session.scalar(select(LLMReservation.id).where(
            LLMReservation.startup_analysis_id == identity).limit(1))
        if item.claim_id is not None or paid:
            _close(item, 'blocked', 'prior_execution')
            return None
        item.claim_id, item.state = claim_id, 'running'
        item.deadline_at = min(item.expires_at, budget.now().replace(microsecond=0) + timedelta(seconds=180))
        result = arguments(item.inputs)
    return result


def _calling(session, identity, effective_messages):
    item = _row(session, StartupAnalysisJob, identity)
    if (item is None or item.state != 'running' or not item.claim_id
            or item.deadline_at is None or budget.now() >= min(item.deadline_at, item.expires_at)
            or digest(effective_messages) != item.prompt_hash):
        raise budget.BudgetError('Persisted current discovery execution required')
    _current(session, item)
    if budget.now() >= min(item.deadline_at, item.expires_at):
        raise budget.BudgetError('Discovery execution expired')
    return item


def check(identity, effective_messages):
    with budget.transaction() as session:
        _calling(session, identity, effective_messages)


def admit(session, identity, effective_messages, config):
    item = _calling(session, identity, effective_messages)
    attempts = session.scalars(select(LLMReservation).where(LLMReservation.startup_analysis_id == identity)).all()
    if (len(attempts) >= 3 or any(row.config_id == config.id for row in attempts)
            or any(row.state not in ('settled',) for row in attempts)):
        raise budget.BudgetError('Discovery provider attempt unavailable')
    current = _row(session, LLMConfig, config.id)
    keys = ('provider', 'model', 'api_base_url', 'api_key_env_var', 'is_active', 'is_default',
            'tasks', 'role', 'priority', 'max_tokens', 'temperature', 'billing_input_limit',
            'billing_output_limit', 'cost_per_1k_input', 'cost_per_1k_output')
    if current is None or not current.is_active or any(getattr(current, k) != getattr(config, k) for k in keys):
        raise budget.BudgetError('Discovery model configuration changed')
    # Row-lock/configuration reads may have blocked after the first check.
    if budget.now() >= min(item.deadline_at, item.expires_at):
        raise budget.BudgetError('Discovery execution expired')


def finish(identity, claim_id, analysis):
    from app.crawlers.startup_discovery import _infer_sector
    from app.llm.tasks import _save_revision
    if analysis.get('website') and not website(analysis['website']):
        raise budget.BudgetError('Discovery website result unavailable')
    with budget.transaction() as session:
        item = _row(session, StartupAnalysisJob, identity)
        if item is None or item.state != 'running' or item.claim_id != claim_id:
            return
        if budget.now() >= min(item.deadline_at, item.expires_at):
            _close(item, 'blocked', 'execution_expired')
            return
        try:
            company = _current(session, item)
        except (budget.BudgetError, ValueError, TypeError, KeyError, AttributeError):
            _close(item, 'stale', 'inputs_unavailable')
            return
        if budget.now() >= min(item.deadline_at, item.expires_at):
            _close(item, 'blocked', 'execution_expired')
            return
        _save_revision(company, new_data=analysis, source='startup-discovery', trigger=f'Analysis job {identity}')
        company.ai_analysis, company.ai_analysis_at = analysis, budget.now().replace(microsecond=0)
        if not company.website:
            company.website = website(analysis.get('website'))
        if not company.sector:
            company.sector = _infer_sector(analysis)
        _close(item, 'succeeded', 'initial_analysis_saved')


def fail(identity, claim_id):
    with budget.transaction() as session:
        item = _row(session, StartupAnalysisJob, identity)
        # Ownership also fences exception handling after commit ACK loss.
        if item is None or item.state != 'running' or item.claim_id != claim_id:
            return
        try:
            company = _current(session, item)
        except (budget.BudgetError, ValueError, TypeError, KeyError, AttributeError):
            _close(item, 'stale', 'inputs_unavailable')
            return
        company.ai_analysis_failures = Company.ai_analysis_failures + 1
        _close(item, 'blocked', 'execution_unavailable')


def recover():
    with Session(db.engine) as session:
        ids = list(session.scalars(select(StartupAnalysisJob.id).where(
            or_(and_(StartupAnalysisJob.state == 'queued', StartupAnalysisJob.next_dispatch_at <= budget.now()),
                and_(StartupAnalysisJob.state == 'running', or_(StartupAnalysisJob.deadline_at <= budget.now(),
                                                               StartupAnalysisJob.deadline_at.is_(None))))
        ).order_by(StartupAnalysisJob.next_dispatch_at, StartupAnalysisJob.id).limit(50)))
    for identity in ids:
        dispatch = False
        with budget.transaction() as session:
            item = _row(session, StartupAnalysisJob, identity)
            if item is None or item.state not in ('queued', 'running'):
                continue
            timestamp = budget.now()
            if timestamp >= item.expires_at or (item.state == 'running' and (
                    item.deadline_at is None or timestamp >= item.deadline_at)):
                _close(item, 'blocked', 'execution_expired')
            elif item.state == 'queued':
                try:
                    _current(session, item)
                except (budget.BudgetError, ValueError, TypeError, KeyError, AttributeError):
                    _close(item, 'stale', 'inputs_unavailable')
                else:
                    dispatch = True
        if dispatch:
            publish(identity)
