from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('frenchweb')
class FrenchWebCrawler(RSSCrawler):
    """Crawler for FrenchWeb - French startup and tech ecosystem news."""
    pass
