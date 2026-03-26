from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('silicon-fr')
class SiliconFrCrawler(RSSCrawler):
    """Crawler for Silicon.fr - French enterprise IT news."""
    pass
