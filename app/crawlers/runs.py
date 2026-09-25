"""Per-source run claims with fencing; the only way crawl results are written (spec §5).

Lock order everywhere: news_source -> crawl_source_state -> crawl_source_profile.
"""
from dataclasses import dataclass
from datetime import datetime
import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.crawl_runtime import CrawlSourceState
from app.models.crawl_schema import CrawlSourceProfile
from app.models.source import CrawlLog, NewsSource
from . import schedule

logger = logging.getLogger(__name__)


class RunLost(Exception):
    """The claim, fence, lease or activation changed; the caller must not write."""


@dataclass(frozen=True)
class Claim:
    source_id: int
    claim_id: str
    fence: int
    log_id: int
    activation_generation: int
    started_at: datetime


def _state(session, source_id):
    return session.scalar(select(CrawlSourceState).where(CrawlSourceState.source_id == source_id)
                          .with_for_update().execution_options(populate_existing=True))


def _activation(session, source_id):
    profile = session.scalar(select(CrawlSourceProfile).where(CrawlSourceProfile.source_id == source_id)
                             .with_for_update().execution_options(populate_existing=True))
    return profile.activation_generation if profile else 0


def _live(state, moment):
    return state.claim_id is not None and state.lease_expires_at is not None and state.lease_expires_at > moment


def _begin(session):
    # pysqlite legacy mode does not BEGIN before SELECT/SAVEPOINT; RELEASE would commit.
    connection = session.connection()
    if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql('BEGIN')


def ensure_states(moment):
    """Give every active source a state row, computed with the normal rule (spec §12.1)."""
    try:
        with Session(db.engine) as session, session.begin():
            hour, zone = schedule.anchor_settings(session)
            rows = session.execute(
                select(NewsSource.id, NewsSource.last_crawled_at, NewsSource.crawl_frequency_minutes)
                .outerjoin(CrawlSourceState, CrawlSourceState.source_id == NewsSource.id)
                .where(NewsSource.is_active.is_(True), CrawlSourceState.source_id.is_(None))).all()
            for source_id, last, frequency in rows:
                due = moment if last is None else max(moment, schedule.next_due(
                    error_code=None, started=last, finished=last, frequency=frequency,
                    failures=0, retry_after=None, hour=hour, zone=zone))
                session.add(CrawlSourceState(source_id=source_id, next_due_at=due, due_reason='initial'))
    except IntegrityError:
        logger.info('Crawl state rows were created concurrently; retrying next round')


def claim(source_id, *, due_only):
    moment = schedule.now()
    with Session(db.engine) as session, session.begin():
        state = _state(session, source_id)
        source = session.get(NewsSource, source_id)
        if state is None or source is None or not source.is_active:
            return None
        if (due_only and state.next_due_at > moment) or _live(state, moment):
            return None
        if state.running_log_id is not None:
            old = session.get(CrawlLog, state.running_log_id)
            if old is not None and old.status == 'running':
                old.status, old.outcome, old.error_code, old.finished_at = 'failed', 'lease_expired', 'lease_expired', moment
        activation = _activation(session, source_id)
        identity = str(uuid.uuid4())
        log = CrawlLog(source_id=source_id, started_at=moment, status='running', claim_id=identity,
                       fence=state.fence + 1, activation_generation=activation)
        session.add(log)
        session.flush()
        state.fence, state.claim_id, state.due_reason = state.fence + 1, identity, 'claimed'
        state.lease_expires_at, state.running_log_id = moment + schedule.LEASE, log.id
        return Claim(source_id, identity, state.fence, log.id, activation, moment)


def claim_due(limit=50):
    moment = schedule.now()
    ensure_states(moment)
    with Session(db.engine) as session:
        ids = list(session.scalars(
            select(CrawlSourceState.source_id).join(NewsSource, NewsSource.id == CrawlSourceState.source_id)
            .where(NewsSource.is_active.is_(True), CrawlSourceState.next_due_at <= moment,
                   or_(CrawlSourceState.claim_id.is_(None), CrawlSourceState.lease_expires_at <= moment))
            .order_by(CrawlSourceState.next_due_at, CrawlSourceState.source_id).limit(limit)))
    return [item for item in (claim(source_id, due_only=True) for source_id in ids) if item is not None]


def current(source_id, claim_id):
    moment = schedule.now()
    with Session(db.engine) as session:
        state = session.get(CrawlSourceState, source_id)
        if state is None or state.claim_id != claim_id or not _live(state, moment):
            return None
        log = session.get(CrawlLog, state.running_log_id)
        return Claim(source_id, claim_id, state.fence, log.id, log.activation_generation or 0, log.started_at)


def lock(session, claim):
    """Inside the final transaction: lock rows and prove the claim is still current."""
    _begin(session)
    session.scalar(select(NewsSource.id).where(NewsSource.id == claim.source_id).with_for_update())
    state = _state(session, claim.source_id)
    if (state is None or state.claim_id != claim.claim_id or state.fence != claim.fence
            or not _live(state, schedule.now())
            or _activation(session, claim.source_id) != claim.activation_generation):
        raise RunLost()
    return state


def settle(session, state, claim, *, status, route, error_code=None, found=0, new=0, retry_after=None, message=None):
    """Finish a claimed run in the caller's final transaction: log, schedule, attention, lease."""
    moment = schedule.now()
    source = session.get(NewsSource, claim.source_id)
    category = schedule.kind(error_code)
    failures = 0 if category == 'ok' else state.consecutive_failures + 1
    hour, zone = schedule.anchor_settings(session)
    state.next_due_at = schedule.next_due(
        error_code=error_code, started=claim.started_at, finished=moment, frequency=source.crawl_frequency_minutes,
        failures=failures, retry_after=retry_after, hour=hour, zone=zone)
    state.due_reason = {'ok': 'schedule', 'retry': 'retry', 'blocked': 'cooldown', 'extraction': 'schedule'}[category]
    state.consecutive_failures = failures
    state.claim_id = state.lease_expires_at = state.running_log_id = None
    if category == 'ok':
        source.last_crawled_at = moment
        state.attention_reason = state.attention_since = None
    elif category == 'blocked' or (category == 'extraction' and failures >= schedule.EXTRACTION_ATTENTION):
        reason = error_code if category == 'blocked' else 'extraction_failed'
        if state.attention_reason != reason:
            state.attention_reason, state.attention_since = reason, moment
    log = session.get(CrawlLog, claim.log_id)
    log.status = 'success' if category == 'ok' else 'failed'
    log.outcome = status if category == 'ok' else ('blocked' if category == 'blocked' else 'failed')
    log.route, log.error_code = log.route or route, error_code
    log.articles_found, log.articles_new = found, new
    text = message or error_code
    log.error_message = text[:2000] if text else None
    log.finished_at = moment


def mark_stale(claim):
    moment = schedule.now()
    with Session(db.engine) as session, session.begin():
        state = _state(session, claim.source_id)
        log = session.get(CrawlLog, claim.log_id)
        if log is not None and log.status == 'running':
            log.status, log.outcome, log.finished_at = 'failed', 'stale', moment
        if state is not None and state.claim_id == claim.claim_id and state.fence == claim.fence:
            state.claim_id = state.lease_expires_at = state.running_log_id = None


def abandon(claim, *, route, error_code, found=0, retry_after=None, message=None):
    """Record a failed claimed run in its own transaction; a lost claim only marks its log stale."""
    try:
        with Session(db.engine) as session, session.begin():
            state = lock(session, claim)
            settle(session, state, claim, status='failed', route=route, error_code=error_code, found=found,
                   retry_after=retry_after, message=message)
    except RunLost:
        mark_stale(claim)
    except SQLAlchemyError:
        logger.warning('Crawl failure for source %s could not be recorded; the lease will expire', claim.source_id)


def request_now(source_id):
    """Admin/old-message request: due now unless a live claim is already running (spec §5.6)."""
    moment = schedule.now()
    with Session(db.engine) as session, session.begin():
        source = session.get(NewsSource, source_id)
        if source is None or not source.is_active:
            return 'inactive'
        state = _state(session, source_id)
        if state is None:
            session.add(CrawlSourceState(source_id=source_id, next_due_at=moment, due_reason='manual'))
            return 'queued'
        if _live(state, moment):
            return 'running'
        state.next_due_at, state.due_reason = min(state.next_due_at, moment), 'manual'
        return 'queued'


def record_route(claim, route):
    with Session(db.engine) as session, session.begin():
        log = session.get(CrawlLog, claim.log_id)
        if log is not None and log.status == 'running':
            log.route, log.schema_version_id, log.policy_version_id = route.kind, route.version_id, route.policy_version_id


def execute(source_id, claim_id):
    """Resolve the route for a current claim and run it; approval is enforced here (spec §4.5)."""
    from app.crawlers import activation, registry
    from app.crawlers.engine import CrawlEngine
    claim = current(source_id, claim_id)
    if claim is None:
        return None
    try:
        route = activation.route(claim)
    except RunLost:
        mark_stale(claim)
        return None
    except activation.Blocked as blocked:
        abandon(claim, route='schema', error_code=blocked.code)
        return None
    finally:
        db.session.remove()
    record_route(claim, route)
    if route.kind == 'schema':
        engine = CrawlEngine(source_id, recipe=route.recipe, fetch_policy=route.fetch_policy, profile=route.quality)
        return engine.run(claim)
    try:
        crawler = registry.get_crawler(db.session.get(NewsSource, source_id))
    except Exception as exc:
        abandon(claim, route='legacy', error_code='crawler_error', message=str(exc))
        return None
    return crawler.run(claim)
