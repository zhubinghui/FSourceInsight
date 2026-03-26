from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('cea-leti')
class CeaLetiCrawler(HTMLCrawler):
    """Crawler for CEA-Leti - microelectronics research institute in Grenoble."""

    ARTICLE_LIST_SELECTOR = '.news-item, .press-release, article'
    TITLE_SELECTOR = 'h2 a, h3 a, .field-title a'
    LINK_SELECTOR = 'h2 a, h3 a, .field-title a'
    CONTENT_SELECTOR = '.field-summary, .teaser, p'
    DATE_SELECTOR = '.date, time, .field-date'
    IMAGE_SELECTOR = 'img'
