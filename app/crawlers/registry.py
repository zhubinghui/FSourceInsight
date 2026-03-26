import importlib
import logging
from typing import Type

from app.models.source import NewsSource
from .base import BaseCrawler
from .rss_crawler import RSSCrawler

logger = logging.getLogger(__name__)

# Maps source slug to crawler class for sources that need custom parsers
_CRAWLER_REGISTRY: dict[str, Type[BaseCrawler]] = {}


def register_crawler(slug: str):
    """Decorator to register a crawler class for a specific source slug."""
    def decorator(cls):
        _CRAWLER_REGISTRY[slug] = cls
        return cls
    return decorator


def get_crawler(source: NewsSource) -> BaseCrawler:
    """Get the appropriate crawler instance for a news source."""
    # Check registry first (source-specific crawlers)
    if source.slug in _CRAWLER_REGISTRY:
        return _CRAWLER_REGISTRY[source.slug](source)

    # If a custom crawler_class is specified in DB, try to import it
    if source.crawler_class:
        try:
            module_path, class_name = source.crawler_class.rsplit('.', 1)
            module = importlib.import_module(f'app.crawlers.{module_path}')
            cls = getattr(module, class_name)
            return cls(source)
        except (ImportError, AttributeError) as e:
            logger.error(f'Failed to load crawler {source.crawler_class}: {e}')

    # Default: use generic RSS crawler for rss/atom, raise for html_scrape
    if source.feed_type in ('rss', 'atom'):
        return RSSCrawler(source)

    raise ValueError(
        f'No crawler registered for source {source.slug} (feed_type={source.feed_type})'
    )


def discover_crawlers():
    """Import all source modules to trigger @register_crawler decorators."""
    import app.crawlers.sources  # noqa: F401
