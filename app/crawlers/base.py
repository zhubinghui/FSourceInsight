import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.article import Article
from app.models.source import NewsSource
from .fetcher import FetchError

logger = logging.getLogger(__name__)


@dataclass
class RawArticle:
    """Intermediate representation of a crawled article before DB insertion."""
    title: str
    url: str
    external_id: str
    content: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None


@dataclass
class CrawlResult:
    articles_found: int = 0
    articles_new: int = 0
    errors: list = field(default_factory=list)
    status: str = 'running'
    retryable: bool = False
    retry_after: int | None = None


class LegacyFailure(Exception):
    """A classified legacy failure; its code feeds the schedule (spec §5.4)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def failure_code(exc):
    """Map a legacy exception to (crawl error code, Retry-After seconds or None)."""
    from celery.exceptions import SoftTimeLimitExceeded
    if isinstance(exc, LegacyFailure):
        return exc.code, None
    if isinstance(exc, SoftTimeLimitExceeded):
        return 'timeout', None
    if isinstance(exc, FetchError):
        return exc.code, exc.retry_after
    if isinstance(exc, requests.Timeout):
        return 'timeout', None
    if isinstance(exc, requests.ConnectionError):
        return 'network_error', None
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 429:
            hint = exc.response.headers.get('Retry-After', '')
            return 'rate_limited', int(hint) if hint.isdigit() else None
        if status == 408:
            return 'timeout', None
        if status >= 500:
            return 'server_error', None
        return ('forbidden' if status in (401, 403) else 'http_error'), None
    if isinstance(exc, SQLAlchemyError):
        return 'database_error', None
    if isinstance(exc, ValueError):
        return 'invalid_article', None
    return 'crawler_error', None


class BaseCrawler(ABC):
    """Legacy crawl pipeline. A source must be committed before running it.

    Runs only under a claim: articles, their LLM jobs, the run log and the next
    due time are written in one fenced transaction (spec §5.3).
    """

    def __init__(self, source: NewsSource):
        self.source = source
        self.empty_result_is_valid = False
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')

    @abstractmethod
    def fetch_articles(self) -> list[RawArticle]:
        raise NotImplementedError

    def _validated(self, articles):
        """Normalize entries; any invalid required field fails the whole run (as before)."""
        from app.utils.text import strip_html
        rows = []
        for raw in articles:
            title = strip_html(raw.title)
            url = urlsplit(raw.url)
            if (not title or not title.strip() or len(title) > 500
                    or url.scheme not in {'http', 'https'} or not url.hostname
                    or url.username is not None or url.password is not None
                    or len(raw.url) > 1000 or any(ord(c) < 32 for c in raw.url)
                    or not raw.external_id or len(raw.external_id) > 500):
                raise ValueError('Invalid article title, HTTP(S) URL or external identity')
            published_at = raw.published_at
            if published_at is not None and published_at.tzinfo is not None:
                published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
            rows.append(dict(external_id=raw.external_id, url=raw.url, title_fr=title,
                             content_fr=strip_html(raw.content), author=(raw.author or '')[:200] or None,
                             image_url=(raw.image_url or '')[:1000] or None, published_at=published_at))
        return rows

    def _insert(self, session, rows):
        """Insert unseen identities; a competing insert of the same identity is tolerated."""
        seen = set(session.scalars(select(Article.external_id).where(
            Article.source_id == self.source.id, Article.external_id.in_([r['external_id'] for r in rows]))))
        ids = []
        for row in rows:
            if row['external_id'] in seen:
                continue
            seen.add(row['external_id'])
            article = Article(source_id=self.source.id, **row)
            try:
                with session.begin_nested():
                    session.add(article)
                    session.flush()
            except IntegrityError:
                # Current read on MySQL also sees a concurrent commit. Do not mask other violations.
                if session.scalar(select(Article.id).where(Article.source_id == self.source.id,
                                  Article.external_id == row['external_id']).with_for_update()) is None:
                    raise
                continue
            ids.append(article.id)
        return ids

    def run(self, claim) -> CrawlResult:
        """Fetch without locks, then write articles, LLM jobs, log and schedule in one claimed commit."""
        from app.crawlers import runs
        from app.llm import article_jobs
        result, jobs = CrawlResult(), []
        name = self.source.name
        try:
            raw_articles = self.fetch_articles()
            result.articles_found = len(raw_articles)
            if not raw_articles and not self.empty_result_is_valid:
                raise LegacyFailure('empty_extraction', 'Empty extraction without evidence of a valid empty source')
            rows = self._validated(raw_articles)
            with Session(db.engine) as session, session.begin():
                state = runs.lock(session, claim)
                ids = self._insert(session, rows) if rows else []
                jobs = [job for job in (article_jobs.enqueue(session, article_id, 'crawl', crawl_log_id=claim.log_id)
                                        for article_id in ids) if job]
                result.articles_new = len(ids)
                result.status = 'success' if ids else 'no_change'
                runs.settle(session, state, claim, status=result.status, route='legacy',
                            found=result.articles_found, new=result.articles_new)
        except runs.RunLost:
            runs.mark_stale(claim)
            result.status, result.articles_new, result.errors = 'stale', 0, ['stale_claim']
            return result
        except Exception as exc:
            code, retry_after = failure_code(exc)
            result.status, result.articles_new, result.retry_after = 'failed', 0, retry_after
            result.errors.append(str(exc))
            self.logger.error('Crawl failed for %s: %s', name, exc)
            runs.abandon(claim, route='legacy', error_code=code, found=result.articles_found,
                         retry_after=retry_after, message=str(exc))
            return result
        for identity in jobs:
            article_jobs.publish(identity)
        self.logger.info('Crawled %s: found=%s new=%s status=%s', name,
                         result.articles_found, result.articles_new, result.status)
        return result
