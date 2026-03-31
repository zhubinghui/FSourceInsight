from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('cea-enterprise')
class CeaEnterpriseCrawler(RSSCrawler):
    """Crawler for CEA Enterprise News — partnership and technology transfer updates.

    RSS feed provides 100 entries covering R&D partnerships, tech transfer,
    patents, and CEA innovations for industry.
    """
    pass
