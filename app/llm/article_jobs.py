"""Durable LLM work for articles: created with the article, claimed before any paid call (spec §6).

At most one queued/running job per article. Transitions are short row-locked
transactions; the model is only called by a consumer holding the claim.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob

TASK = 'app.llm.article_tasks.process'
QUEUE_LIFETIME = timedelta(hours=24)
RUNNING_LIMIT = timedelta(minutes=30)
SPACING = timedelta(seconds=121)
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _row(session, identity):
    return session.scalar(select(ArticleLLMJob).where(ArticleLLMJob.id == identity).with_for_update()
                          .execution_options(populate_existing=True))


def _close(item, state, reason):
    item.state, item.reason = state, reason
    item.finished_at, item.active_article_id = now(), None


def enqueue(session, article_id, trigger, *, crawl_log_id=None, force=False):
    """Create a queued job inside the caller's transaction; None if one is already active."""
    if session.scalar(select(ArticleLLMJob.id).where(ArticleLLMJob.active_article_id == article_id)):
        return None
    moment = now()
    item = ArticleLLMJob(id=str(uuid.uuid4()), article_id=article_id, active_article_id=article_id,
                         trigger=trigger, crawl_log_id=crawl_log_id, force=force, state='queued',
                         created_at=moment, next_dispatch_at=moment, expires_at=moment + QUEUE_LIFETIME)
    session.add(item)
    session.flush()
    return item.id


def request(article_id, trigger, *, force=False):
    """Own transaction (Admin, retired messages). Returns (job id, created)."""
    with Session(db.engine) as session, session.begin():
        if session.scalar(select(Article.id).where(Article.id == article_id).with_for_update()) is None:
            return None, False
        active = session.scalar(select(ArticleLLMJob.id).where(ArticleLLMJob.active_article_id == article_id))
        if active:
            return active, False
        return enqueue(session, article_id, trigger, force=force), True


def publish(identity):
    from celery_app import celery
    try:
        with Session(db.engine) as session, session.begin():
            item = _row(session, identity)
            if item is None or item.state != 'queued' or now() < item.next_dispatch_at:
                return
            if now() >= item.expires_at:
                _close(item, 'expired', 'queue_expired')
                return
            item.next_dispatch_at = now() + SPACING
        celery.send_task(TASK, args=[identity], queue='llm')
    except Exception:
        logger.warning('Article LLM dispatch unavailable; durable job retained')


def claim(identity, claim_id):
    with Session(db.engine) as session, session.begin():
        item = _row(session, identity)
        if item is None or item.state != 'queued' or item.claim_id is not None:
            return None
        if now() >= item.expires_at:
            _close(item, 'expired', 'queue_expired')
            return None
        if item.article_id is None:
            _close(item, 'failed', 'article_unavailable')
            return None
        item.state, item.claim_id, item.deadline_at = 'running', claim_id, now() + RUNNING_LIMIT
        return SimpleNamespace(article_id=item.article_id, force=item.force)


def finish(identity, claim_id, state, reason):
    with Session(db.engine) as session, session.begin():
        item = _row(session, identity)
        if item is None or item.state != 'running' or item.claim_id != claim_id:
            logger.info('Article LLM job %s finished after losing its claim', identity)
            return
        _close(item, state, reason)


def recover(limit=50):
    moment = now()
    with Session(db.engine) as session:
        ids = list(session.scalars(select(ArticleLLMJob.id).where(or_(
            and_(ArticleLLMJob.state == 'queued', ArticleLLMJob.next_dispatch_at <= moment),
            and_(ArticleLLMJob.state == 'running', ArticleLLMJob.deadline_at <= moment)))
            .order_by(ArticleLLMJob.next_dispatch_at, ArticleLLMJob.id).limit(limit)))
    for identity in ids:
        dispatch = False
        with Session(db.engine) as session, session.begin():
            item = _row(session, identity)
            if item is None:
                continue
            if item.state == 'running' and item.deadline_at is not None and item.deadline_at <= now():
                # A paid call may have happened; never pay again automatically.
                _close(item, 'failed', 'interrupted')
            elif item.state == 'queued':
                if now() >= item.expires_at:
                    _close(item, 'expired', 'queue_expired')
                else:
                    dispatch = True
        if dispatch:
            publish(identity)


def latest(article_id):
    """Active job first (timestamps are whole seconds and ids are random), then the newest."""
    return db.session.scalar(select(ArticleLLMJob).where(ArticleLLMJob.article_id == article_id)
                             .order_by(ArticleLLMJob.active_article_id.is_(None), ArticleLLMJob.created_at.desc(),
                                       ArticleLLMJob.finished_at.desc()).limit(1))


def counts():
    return dict(db.session.execute(select(ArticleLLMJob.state, func.count()).group_by(ArticleLLMJob.state)).all())


def backfill(*, apply=False, batch=500):
    """Jobs for unprocessed articles without an active job. Dry run by default; returns the count."""
    active = select(ArticleLLMJob.active_article_id).where(ArticleLLMJob.active_article_id.is_not(None))
    with Session(db.engine) as session:
        ids = list(session.scalars(select(Article.id).where(
            Article.llm_processed.is_(False), Article.id.not_in(active)).order_by(Article.id)))
    if not apply:
        return len(ids)
    created = 0
    for start in range(0, len(ids), batch):
        with Session(db.engine) as session, session.begin():
            created += sum(1 for article_id in ids[start:start + batch] if enqueue(session, article_id, 'backfill'))
    return created
