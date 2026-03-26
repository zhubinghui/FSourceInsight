from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('maddyness')
class MaddynessCrawler(RSSCrawler):
    """Crawler for Maddyness - French startup ecosystem and innovation news."""
    pass
