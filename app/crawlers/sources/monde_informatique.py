from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('monde-informatique')
class MondeInformatiqueCrawler(RSSCrawler):
    """Crawler for Le Monde Informatique - French enterprise IT news."""
    pass
