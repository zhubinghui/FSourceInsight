from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler


@register_crawler('inovallee')
class InovalleeCrawler(RSSCrawler):
    """Crawler for Inovallée — Grenoble tech park ecosystem news.

    Covers startups, events, and ecosystem updates from the Inovallée
    technology park in Meylan, near Grenoble.
    """
    pass
