from datetime import datetime

import pytest
import requests
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.crawlers.base import BaseCrawler, RawArticle
from app.crawlers.html_crawler import HTMLCrawler
from app.crawlers.rss_crawler import RSSCrawler
from app.models.article import Article
from app.models.source import NewsSource, CrawlLog


@pytest.fixture
def source(db):
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid/directory/',
                        feed_url='https://test.invalid/feed', category='national')
    db.session.add(source)
    db.session.commit()
    return source


class FixtureCrawler(BaseCrawler):
    def __init__(self, source, articles):
        super().__init__(source)
        self.articles = articles

    def fetch_articles(self):
        return self.articles


def test_run_deduplicates_batch_and_repeated_crawls(db, source):
    item = RawArticle(title='Research', url='https://test.invalid/news', external_id='guid-1')
    crawler = FixtureCrawler(source, [item, item])
    first = crawler.run()
    assert first.articles_new == 1 and not first.errors
    assert crawler.run().articles_new == 0
    assert Article.query.count() == 1
    assert all(log.status == 'success' for log in CrawlLog.query.all())


def test_database_failure_rolls_back_and_finishes_log(db, source):
    def storage_unavailable(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO article '):
            raise OperationalError(statement, parameters, RuntimeError('synthetic database failure'))

    event.listen(db.engine, 'before_cursor_execute', storage_unavailable)
    try:
        result = FixtureCrawler(source, [RawArticle('Research', 'https://test.invalid/news', 'one')]).run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', storage_unavailable)
    assert result.articles_new == 0 and result.errors
    assert Article.query.count() == 0
    log = CrawlLog.query.one()
    assert log.status == 'failed' and log.finished_at is not None
    # Business session remains usable after failure.
    assert db.session.get(NewsSource, source.id) is not None


def test_late_database_failure_rolls_back_the_whole_article_batch(db, source):
    def fail_second_insert(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO article ') and 'two' in parameters:
            raise OperationalError(statement, parameters, RuntimeError('second insert failed'))
    event.listen(db.engine, 'before_cursor_execute', fail_second_insert)
    try:
        result = FixtureCrawler(source, [
            RawArticle('First', 'https://test.invalid/one', 'one'),
            RawArticle('Second', 'https://test.invalid/two', 'two'),
        ]).run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_second_insert)
    assert result.errors and result.articles_new == 0
    assert Article.query.count() == 0
    assert CrawlLog.query.one().status == 'failed'


def test_unconfirmed_empty_extraction_is_not_success(db, source):
    result = FixtureCrawler(source, []).run()
    assert result.errors
    assert CrawlLog.query.one().status == 'failed'
    assert source.last_crawled_at is None


def http_response(body, url, status=200):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content = body.encode()
    response.encoding = 'utf-8'
    return response


def test_html_run_resolves_links_and_persists_utc(db, source, monkeypatch):
    html = '''<article><h2><a href="/news/one">Research</a></h2>
    <time datetime="2026-07-01T12:00:00+02:00"></time><div class="content">Article content</div></article>'''
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: http_response(html, source.url))
    result = HTMLCrawler(source).run()
    assert not result.errors
    row = Article.query.one()
    assert row.url == 'https://test.invalid/news/one'
    assert row.published_at == datetime(2026, 7, 1, 10)


def test_valid_empty_rss_is_not_a_failure(db, source, monkeypatch):
    rss = '<rss version="2.0"><channel><title>Empty feed</title><link>https://test.invalid</link><description>Quiet source</description></channel></rss>'
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: http_response(rss, source.feed_url))
    result = RSSCrawler(source).run()
    assert result.articles_new == 0 and not result.errors
    assert CrawlLog.query.one().status == 'success'


@pytest.mark.parametrize('status', [429, 503])
def test_transient_http_failure_requests_celery_retry(db, source, monkeypatch, status):
    from celery.exceptions import Retry
    from app.crawlers.tasks import crawl_source

    calls = []
    def fetch(*args, **kwargs):
        calls.append(args[0])
        return http_response('unavailable', source.feed_url, status)
    monkeypatch.setattr(requests, 'get', fetch)
    crawl_source.push_request(is_eager=True, called_directly=False, retries=0)
    try:
        with pytest.raises(Retry):
            crawl_source.run(source.id)
    finally:
        crawl_source.pop_request()
    assert calls == [source.feed_url]
    assert CrawlLog.query.one().status == 'failed'


def test_forbidden_source_is_reported_without_learning_or_retry(db, source, monkeypatch):
    from app.crawlers.tasks import crawl_source
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: http_response('forbidden', source.feed_url, 403))
    result = crawl_source.run(source.id)
    assert result['errors'] and result['new'] == 0
    assert result['status'] == 'failed' and not result['retryable']


def test_rss_dates_are_utc_independent_of_worker_dst(db, source, monkeypatch):
    import time
    rss = '<rss version="2.0"><channel><title>News</title><item><title>Research</title><link>https://test.invalid/news</link><pubDate>Wed, 01 Jul 2026 12:00:00 +0200</pubDate></item></channel></rss>'
    try:
        with monkeypatch.context() as patch:
            patch.setenv('TZ', 'Europe/Paris')
            time.tzset()
            patch.setattr(requests, 'get', lambda *a, **kw: http_response(rss, source.feed_url))
            assert not RSSCrawler(source).run().errors
    finally:
        time.tzset()
    assert Article.query.one().published_at == datetime(2026, 7, 1, 10)


@pytest.mark.parametrize('title,url', [('', 'https://test.invalid/news'), ('<p></p>', 'https://test.invalid/news'), ('Research', 'javascript:alert(1)')])
def test_invalid_required_fields_never_enter_articles(db, source, title, url):
    result = FixtureCrawler(source, [RawArticle(title, url, 'bad')]).run()
    assert result.errors
    assert Article.query.count() == 0
