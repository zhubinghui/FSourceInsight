from app.crawlers.registry import register_crawler
from app.crawlers.html_crawler import HTMLCrawler


@register_crawler('french-tech-alps')
class FrenchTechAlpsCrawler(HTMLCrawler):
    """Crawler for French Tech in the Alps - Grenoble startup community."""

    ARTICLE_LIST_SELECTOR = 'article.post'
    TITLE_SELECTOR = '.entry-title a'
    LINK_SELECTOR = '.entry-title a'
    CONTENT_SELECTOR = '.entry-summary'
    DATE_SELECTOR = 'time.entry-date'
    IMAGE_SELECTOR = '.post-thumbnail img'
