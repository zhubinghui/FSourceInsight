import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import requests
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.article import Article
from app.models.source import NewsSource, CrawlLog

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


class BaseCrawler(ABC):
    """Legacy crawl pipeline. A source must be committed before running it.

    Full content-quality profiles, source leases and the ingestion outbox are
    supplied by the later schema engine; this adapter only enforces basic validity.
    """

    def __init__(self, source: NewsSource):
        self.source = source
        self.empty_result_is_valid = False
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')

    @abstractmethod
    def fetch_articles(self) -> list[RawArticle]:
        raise NotImplementedError

    def dedup(self, articles: list[RawArticle]) -> list[RawArticle]:
        """Deduplicate both a single response and already persisted identities."""
        if not articles:
            return []
        external_ids = [a.external_id for a in articles]
        seen = set(
            row[0] for row in db.session.query(Article.external_id).filter(
                Article.source_id == self.source.id,
                Article.external_id.in_(external_ids),
            ).all()
        )
        unique = []
        for article in articles:
            if article.external_id not in seen:
                unique.append(article)
                seen.add(article.external_id)
        return unique

    def save(self, articles: list[RawArticle]) -> int:
        """Commit valid entries, tolerating a competing insert of the same identity."""
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
            rows.append(Article(
                source_id=self.source.id, external_id=raw.external_id, url=raw.url,
                title_fr=title, content_fr=strip_html(raw.content),
                author=(raw.author or '')[:200] or None,
                image_url=(raw.image_url or '')[:1000] or None,
                published_at=published_at,
            ))

        if rows:
            connection = db.session.connection()
            # sqlite3 legacy mode does not BEGIN for SELECT/SAVEPOINT; without
            # this, RELEASE commits each row and a later rollback cannot undo it.
            if (connection.dialect.name == 'sqlite'
                    and not connection.connection.driver_connection.in_transaction):
                connection.exec_driver_sql('BEGIN')
        saved = 0
        for article in rows:
            try:
                with db.session.begin_nested():
                    db.session.add(article)
                    db.session.flush()
                saved += 1
            except IntegrityError:
                # Current read on MySQL also sees a concurrent commit under
                # REPEATABLE READ. Do not mask other constraint violations.
                existing = Article.query.filter_by(
                    source_id=self.source.id, external_id=article.external_id
                ).with_for_update().first()
                if existing is None:
                    raise
        if rows:
            db.session.commit()
        return saved

    def run(self) -> CrawlResult:
        """Fetch -> deduplicate -> ingest, then independently finalize the run log."""
        result = CrawlResult()
        source_id, source_name = self.source.id, self.source.name
        with Session(db.engine) as ledger, ledger.begin():
            log = CrawlLog(source_id=source_id, started_at=datetime.utcnow(), status='running')
            ledger.add(log)
            ledger.flush()
            log_id = log.id

        try:
            raw_articles = self.fetch_articles()
            result.articles_found = len(raw_articles)
            if not raw_articles and not self.empty_result_is_valid:
                raise ValueError('Empty extraction without evidence of a valid empty source')
            result.articles_new = self.save(self.dedup(raw_articles))
            self.source.last_crawled_at = datetime.utcnow()
            db.session.commit()
            result.status = 'success' if result.articles_new else 'no_change'
        except Exception as exc:
            # Always recover the business session before recording a failed run.
            db.session.rollback()
            result.status = 'failed'
            result.errors.append(str(exc))
            result.retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError, OperationalError))
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                result.retryable = exc.response.status_code in {408, 429} or exc.response.status_code >= 500
            self.logger.error('Crawl failed for %s: %s', source_name, exc)

        with Session(db.engine) as ledger, ledger.begin():
            log = ledger.get(CrawlLog, log_id)
            log.status = 'failed' if result.errors else 'success'
            log.articles_found = result.articles_found
            log.articles_new = result.articles_new
            log.error_message = '\n'.join(result.errors) or None
            log.finished_at = datetime.utcnow()
        self.logger.info('Crawled %s: found=%s new=%s status=%s', source_name,
                         result.articles_found, result.articles_new, result.status)
        return result
