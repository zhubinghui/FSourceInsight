from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('sifted')
class SiftedCrawler(RSSCrawler):
    """Crawler for Sifted.eu - European startup and tech news (English)."""
    pass
