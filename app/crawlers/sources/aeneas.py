from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('aeneas')
class AeneasCrawler(RSSCrawler):
    """Crawler for AENEAS - European semiconductor R&D association news and events."""
    pass
