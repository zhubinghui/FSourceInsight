from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('vipress')
class VipressCrawler(RSSCrawler):
    """Crawler for VIPress.net - French electronics industry news."""
    pass
