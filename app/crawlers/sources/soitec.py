from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('soitec')
class SoitecCrawler(HTMLCrawler):
    """Crawler for Soitec press releases - semiconductor substrate technology."""

    ARTICLE_LIST_SELECTOR = '.press-release, .news-item, article, .view-content .views-row'
    TITLE_SELECTOR = 'h2 a, h3 a, .title a, .field-title a'
    LINK_SELECTOR = 'h2 a, h3 a, .title a, .field-title a'
    CONTENT_SELECTOR = '.field-summary, .teaser, .description, p'
    DATE_SELECTOR = 'time, .date, .field-date'
    IMAGE_SELECTOR = 'img'
    DATE_FORMAT = '%B %d, %Y'
