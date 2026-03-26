from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('tribune-aura')
class TribuneAURACrawler(HTMLCrawler):
    """Crawler for La Tribune AURA - Auvergne-Rhone-Alpes regional economic news."""

    ARTICLE_LIST_SELECTOR = 'article, .article-item, .card-article'
    TITLE_SELECTOR = 'h2 a, h3 a, .article-title a'
    LINK_SELECTOR = 'h2 a, h3 a, .article-title a'
    CONTENT_SELECTOR = '.article-excerpt, .chapo, .description, p'
    DATE_SELECTOR = 'time, .date, .article-date'
    AUTHOR_SELECTOR = '.author, .article-author'
    IMAGE_SELECTOR = 'img'
