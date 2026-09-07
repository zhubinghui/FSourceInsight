"""Translate vetted base configuration, never execute legacy fetch/run/custom code."""
from .html_crawler import HTMLCrawler
from .rss_crawler import RSSCrawler


def recipe_for(crawler):
    if type(crawler) not in {RSSCrawler, HTMLCrawler}:
        raise ValueError('Unsupported legacy adapter')
    doc = {'format_version': 1, 'output_contract': 'article.v1', 'target_kind': 'news',
           'source_id': crawler.source.id, 'locale': 'unknown', 'transport': 'http',
           'identity_policy': 'legacy-compatible-url-v1'}
    if type(crawler) is RSSCrawler:
        doc.update(extractor='rss', feed={'url': crawler.source.feed_url, 'fields': {
            'title': 'title', 'url': 'link', 'external_id': 'id', 'content': 'summary',
            'published_at': 'published', 'author': 'author'}})
    else:
        doc['list_pages'] = [{'url': crawler.source.url, 'item_selector': crawler.ARTICLE_LIST_SELECTOR,
                             'fields': {'title': {'selector': crawler.TITLE_SELECTOR, 'read': 'text'},
                                        'url': {'selector': crawler.LINK_SELECTOR, 'read': 'attr', 'attr': 'href'},
                                        'content': {'selector': crawler.CONTENT_SELECTOR, 'read': 'text'},
                                        'author': {'selector': crawler.AUTHOR_SELECTOR, 'read': 'text'},
                                        'published_at': {'selector': crawler.DATE_SELECTOR, 'read': 'attr', 'attr': 'datetime'},
                                        'image_url': {'selector': crawler.IMAGE_SELECTOR, 'read': 'attr', 'attr': 'src'}}}]
    return doc
