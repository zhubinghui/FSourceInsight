from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('minalogic')
class MinalogicCrawler(HTMLCrawler):
    """Crawler for Minalogic cluster - semiconductor and digital tech news from Grenoble."""

    ARTICLE_LIST_SELECTOR = '.news-item, .actualite-item, article'
    TITLE_SELECTOR = 'h2 a, h3 a, .title a'
    LINK_SELECTOR = 'h2 a, h3 a, .title a'
    CONTENT_SELECTOR = '.excerpt, .description, p'
    DATE_SELECTOR = '.date, time'
    IMAGE_SELECTOR = 'img'
