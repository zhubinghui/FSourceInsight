from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('place-grenet')
class PlaceGrenetCrawler(HTMLCrawler):
    """Crawler for Place Gre'net - Grenoble local news including tech and innovation."""

    ARTICLE_LIST_SELECTOR = 'article.post, .entry, .article-item'
    TITLE_SELECTOR = '.entry-title a, h2 a, h3 a'
    LINK_SELECTOR = '.entry-title a, h2 a, h3 a'
    CONTENT_SELECTOR = '.entry-content, .entry-summary, .excerpt'
    DATE_SELECTOR = 'time, .entry-date, .post-date'
    IMAGE_SELECTOR = '.post-thumbnail img, .entry-image img, img'
