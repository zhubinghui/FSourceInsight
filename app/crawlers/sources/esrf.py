from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('esrf')
class ESRFCrawler(RSSCrawler):
    """Crawler for ESRF (European Synchrotron Radiation Facility) news."""
    pass
