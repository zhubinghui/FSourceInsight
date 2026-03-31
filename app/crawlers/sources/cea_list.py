from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('cea-list')
class CeaListCrawler(RSSCrawler):
    """Crawler for CEA-List — digital systems research lab (AI, cybersecurity, sensors).

    RSS feed at /en/feed/ provides English-language research news.
    """
    pass
