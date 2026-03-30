import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

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


class BaseCrawler(ABC):
    """Abstract base class for all news source crawlers."""

    def __init__(self, source: NewsSource):
        self.source = source
        self.logger = logging.getLogger(f'{__name__}.{self.__class__.__name__}')

    @abstractmethod
    def fetch_articles(self) -> list[RawArticle]:
        """Fetch raw articles from the source. Must be implemented by subclasses."""
        raise NotImplementedError

    def dedup(self, articles: list[RawArticle]) -> list[RawArticle]:
        """Filter out articles already in the database."""
        if not articles:
            return []

        external_ids = [a.external_id for a in articles]
        existing = set(
            row[0] for row in
            db.session.query(Article.external_id)
            .filter(
                Article.source_id == self.source.id,
                Article.external_id.in_(external_ids)
            )
            .all()
        )
        return [a for a in articles if a.external_id not in existing]

    def save(self, articles: list[RawArticle]) -> int:
        """Save new articles to the database. Returns count of saved articles."""
        from app.utils.text import strip_html

        saved = 0
        for raw in articles:
            article = Article(
                source_id=self.source.id,
                external_id=raw.external_id,
                url=raw.url,
                title_fr=strip_html(raw.title),
                content_fr=strip_html(raw.content),
                author=raw.author,
                image_url=raw.image_url,
                published_at=raw.published_at,
            )
            db.session.add(article)
            saved += 1

        if saved:
            db.session.commit()
        return saved

    def run(self) -> CrawlResult:
        """Execute the full crawl pipeline: fetch -> dedup -> save."""
        result = CrawlResult()
        crawl_log = CrawlLog(source_id=self.source.id, started_at=datetime.utcnow())
        db.session.add(crawl_log)
        db.session.commit()

        try:
            raw_articles = self.fetch_articles()
            result.articles_found = len(raw_articles)
            self.logger.info(f'Fetched {result.articles_found} articles from {self.source.name}')

            new_articles = self.dedup(raw_articles)
            saved = self.save(new_articles)
            result.articles_new = saved
            self.logger.info(f'Saved {saved} new articles from {self.source.name}')

            # Update source and crawl log
            self.source.last_crawled_at = datetime.utcnow()
            crawl_log.status = 'success'
            crawl_log.articles_found = result.articles_found
            crawl_log.articles_new = result.articles_new

        except Exception as e:
            self.logger.error(f'Crawl failed for {self.source.name}: {e}')
            result.errors.append(str(e))
            crawl_log.status = 'failed'
            crawl_log.error_message = str(e)

        crawl_log.finished_at = datetime.utcnow()
        db.session.commit()
        return result
