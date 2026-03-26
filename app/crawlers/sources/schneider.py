from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('schneider-electric')
class SchneiderElectricCrawler(HTMLCrawler):
    """Crawler for Schneider Electric Newsroom - energy management and IoT."""

    ARTICLE_LIST_SELECTOR = '.press-release, .news-item, article, .card'
    TITLE_SELECTOR = 'h2 a, h3 a, .title a, .card-title a'
    LINK_SELECTOR = 'h2 a, h3 a, .title a, .card-title a'
    CONTENT_SELECTOR = '.description, .summary, .card-text, p'
    DATE_SELECTOR = 'time, .date, .meta-date'
    IMAGE_SELECTOR = 'img'
