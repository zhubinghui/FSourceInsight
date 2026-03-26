from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('usine-digitale')
class UsineDigitaleCrawler(RSSCrawler):
    """Crawler for L'Usine Digitale - major French industrial tech news."""
    pass
