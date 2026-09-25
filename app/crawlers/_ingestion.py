"""Apply a quality-checked preview under a run claim. No model calls or config publication."""
from dataclasses import asdict, replace
import hashlib

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.extensions import db
from app.llm import article_jobs
from app.models.article import Article
from app.models.source import NewsSource
from . import runs, schedule
from .contracts import CrawlError, CrawlOutcome, FieldProvenance


def run(engine, claim):
    with Session(db.engine) as session:
        source = session.get(NewsSource, engine.source_id)
        if not source or not source.is_active:
            raise ValueError('Source unavailable')
        source_input = (source.url, source.feed_url, source.updated_at)
    preview = engine.preview()
    new = updated = 0
    duplicate, ids, errors, jobs = preview.quality.duplicate, [], list(preview.errors), []
    try:
        with Session(db.engine) as session, session.begin():
            state = runs.lock(session, claim)
            source = session.query(NewsSource).filter_by(id=engine.source_id).with_for_update().one()
            if not source.is_active or (source.url, source.feed_url, source.updated_at) != source_input:
                raise ValueError('invalid_schema')
            for value in preview.articles:
                upgraded = False
                query = session.query(Article).filter_by(source_id=source.id)
                existing = query.filter_by(external_id=value.external_id).one_or_none()
                if existing is None:
                    existing = query.filter_by(url=value.url).one_or_none()
                if existing:
                    rank = {'metadata_only': 0, 'excerpt': 1, 'full': 2}
                    old_rank = rank.get(existing.content_level, 2 if existing.content_fr else 0)
                    if rank[value.content_level] <= old_rank:
                        duplicate += 1
                        continue  # Never overwrite equal/better or unknown legacy body.
                    if existing.url != value.url:
                        raise ValueError('invalid_article')
                    article, upgraded = existing, True
                    updated += 1
                    article.llm_processed = False
                    article.llm_processed_at = None
                    for name in ('content_zh', 'content_en', 'insight_zh', 'insight_en',
                                 'summary_fr', 'summary_zh', 'summary_en'):
                        setattr(article, name, None)
                    if article.title_fr != value.title:
                        article.title_zh = article.title_en = None
                else:
                    article = Article(source_id=source.id, external_id=value.external_id, url=value.url)
                    session.add(article)
                    new += 1
                article.title_fr, article.content_fr = value.title, value.content
                article.author, article.image_url = value.author or article.author, value.image_url or article.image_url
                article.published_at = value.published_at.replace(tzinfo=None) if value.published_at else article.published_at
                article.content_level, article.source_language = value.content_level, value.source_language
                fields = {p.field: p for p in value.provenance}
                for name in ('external_id', 'author', 'image_url', 'published_at'):
                    if getattr(article, name) is not None and (name not in fields or getattr(value, name) is None or
                            name == 'external_id' and article.external_id != value.external_id):
                        fields[name] = FieldProvenance(field=name, method='legacy')
                article.crawl_provenance = {'recipe': engine.recipe.fingerprint, 'engine': engine.VERSION,
                                           'quality_profile': asdict(engine.profile),
                                           'fields': [asdict(p) for p in fields.values()],
                                           'content_hash': hashlib.sha256((value.content or '').encode()).hexdigest()}
                session.flush()
                ids.append(article.id)
                job = article_jobs.enqueue(session, article.id, 'upgrade' if upgraded else 'crawl',
                                           crawl_log_id=claim.log_id)
                if job:
                    jobs.append(job)
            quality = replace(preview.quality, new=new, updated=updated, duplicate=duplicate)
            status = preview.status
            if status == 'ready':
                status = 'success' if ids else 'no_change'
                if not ids:
                    quality = replace(quality, no_change_reason='all_duplicates')
            runs.settle(session, state, claim, status='partial' if status == 'degraded' else status,
                        route='schema', error_code=_error_code(status, errors), found=quality.discovered, new=new)
            outcome = CrawlOutcome(run_id=claim.log_id, status=status, quality=quality,
                                   article_ids=tuple(ids), errors=tuple(errors))
    except runs.RunLost:
        runs.mark_stale(claim)
        return CrawlOutcome(run_id=claim.log_id, status='failed',
                            quality=replace(preview.quality, no_change_reason=None),
                            errors=tuple(errors) + (CrawlError(stage='persistence', code='stale_claim'),))
    except (SQLAlchemyError, ValueError) as exc:
        code = 'database_error' if isinstance(exc, SQLAlchemyError) else 'invalid_article'
        errors.append(CrawlError(stage='persistence' if isinstance(exc, SQLAlchemyError) else 'extraction', code=code))
        runs.abandon(claim, route='schema', error_code=code, found=preview.quality.discovered)
        return CrawlOutcome(run_id=claim.log_id, status='failed',
                            quality=replace(preview.quality, no_change_reason=None), errors=tuple(errors))
    for identity in jobs:
        article_jobs.publish(identity)
    return outcome


def _error_code(status, errors):
    """The error code that drives the schedule; None for results that were written."""
    if status in ('success', 'no_change', 'partial', 'degraded'):
        return None
    codes = [error.code for error in errors]
    for category in ('blocked', 'retry'):
        chosen = [code for code in codes if schedule.kind(code) == category]
        if chosen:
            return chosen[0]
    return codes[0] if codes else 'no_evidence'
