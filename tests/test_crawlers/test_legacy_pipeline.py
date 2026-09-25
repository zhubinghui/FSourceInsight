from datetime import datetime, timedelta

import pytest
import requests
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.crawlers.base import BaseCrawler, RawArticle
from app.crawlers.html_crawler import HTMLCrawler
from app.crawlers.rss_crawler import RSSCrawler
from app.models.article import Article
from app.models.source import NewsSource, CrawlLog
from tests.support.runs import claimed


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
    first = crawler.run(claimed(source.id))
    assert first.articles_new == 1 and not first.errors
    assert crawler.run(claimed(source.id)).articles_new == 0
    assert Article.query.count() == 1
    assert all(log.status == 'success' for log in CrawlLog.query.all())


def test_database_failure_rolls_back_and_finishes_log(db, source):
    def storage_unavailable(connection, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO article '):
            raise OperationalError(statement, parameters, RuntimeError('synthetic database failure'))

    event.listen(db.engine, 'before_cursor_execute', storage_unavailable)
    try:
        result = FixtureCrawler(source, [RawArticle('Research', 'https://test.invalid/news', 'one')]).run(claimed(source.id))
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
        ]).run(claimed(source.id))
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_second_insert)
    assert result.errors and result.articles_new == 0
    assert Article.query.count() == 0
    assert CrawlLog.query.one().status == 'failed'


def test_unconfirmed_empty_extraction_is_not_success(db, source):
    result = FixtureCrawler(source, []).run(claimed(source.id))
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


def test_html_run_resolves_links_and_persists_utc(db, source, fetch_network):
    html = '''<article><h2><a href="/news/one">Research</a></h2>
    <time datetime="2026-07-01T12:00:00+02:00"></time><div class="content">Article content</div></article>'''
    fetch_network.configure(routes={source.url: {'body': html}})
    result = HTMLCrawler(source).run(claimed(source.id))
    assert not result.errors
    row = Article.query.one()
    assert row.url == 'https://test.invalid/news/one'
    assert row.published_at == datetime(2026, 7, 1, 10)


def test_valid_empty_rss_is_not_a_failure(db, source, fetch_network):
    rss = '<rss version="2.0"><channel><title>Empty feed</title><link>https://test.invalid</link><description>Quiet source</description></channel></rss>'
    fetch_network.configure(routes={source.feed_url: {'body': rss, 'headers': {'Content-Type': 'application/rss+xml'}}})
    result = RSSCrawler(source).run(claimed(source.id))
    assert result.articles_new == 0 and not result.errors
    assert CrawlLog.query.one().status == 'success'


def test_rss_dates_are_utc_independent_of_worker_dst(db, source, monkeypatch, fetch_network):
    import time
    rss = '<rss version="2.0"><channel><title>News</title><item><title>Research</title><link>https://test.invalid/news</link><pubDate>Wed, 01 Jul 2026 12:00:00 +0200</pubDate></item></channel></rss>'
    try:
        with monkeypatch.context() as patch:
            patch.setenv('TZ', 'Europe/Paris')
            time.tzset()
            fetch_network.configure(routes={source.feed_url: {'body': rss, 'headers': {'Content-Type': 'application/rss+xml'}}})
            assert not RSSCrawler(source).run(claimed(source.id)).errors
    finally:
        time.tzset()
    assert Article.query.one().published_at == datetime(2026, 7, 1, 10)


@pytest.mark.parametrize('title,url', [('', 'https://test.invalid/news'), ('<p></p>', 'https://test.invalid/news'), ('Research', 'javascript:alert(1)')])
def test_invalid_required_fields_never_enter_articles(db, source, title, url):
    result = FixtureCrawler(source, [RawArticle(title, url, 'bad')]).run(claimed(source.id))
    assert result.errors
    assert Article.query.count() == 0


def test_rss_run_never_ingests_from_a_private_feed(db, source, monkeypatch, fetch_network):
    source.feed_url = 'http://169.254.169.254/latest?token=synthetic-secret'
    db.session.commit()
    rss = '<rss version="2.0"><channel><title>Feed</title><item><title>Secret</title><link>https://test.invalid/secret</link></item></channel></rss>'
    # Old external boundary remains instrumented so this is a real unsafe-ingestion red,
    # not merely the global network guard rejecting an unmocked old HTTP client.
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: http_response(rss, source.feed_url))
    result = RSSCrawler(source).run(claimed(source.id))
    assert result.articles_new == 0 and result.errors == ['unsafe_url']
    assert Article.query.count() == 0
    assert not [e for e in fetch_network.events() if e['kind'] == 'connect']


def test_html_uses_final_document_url_for_relative_links(db, source, fetch_network):
    fetch_network.configure(routes={
        source.url: {'status': 302, 'headers': {'Location': '/updates/'}},
        'https://test.invalid/updates/': {'body': '<article><h2><a href="one">Research</a></h2></article>'},
    })
    result = HTMLCrawler(source).run(claimed(source.id))
    assert not result.errors
    assert Article.query.one().url == 'https://test.invalid/updates/one'


@pytest.mark.parametrize('crawler_type', [RSSCrawler, HTMLCrawler])
def test_legacy_crawler_does_not_claim_no_change_without_a_cached_validator(db, source, fetch_network, crawler_type):
    url = source.feed_url if crawler_type is RSSCrawler else source.url
    fetch_network.configure(routes={url: {'status': 304}})
    result = crawler_type(source).run(claimed(source.id))
    assert result.status == 'failed' and result.errors
    assert Article.query.count() == 0


@pytest.mark.parametrize('status, code', [(429, 'rate_limited'), (503, 'server_error')])
def test_transient_http_failure_is_rescheduled_not_retried_by_celery(db, source, fetch_network, status, code):
    from app.models.crawl_runtime import CrawlSourceState
    fetch_network.configure(routes={source.feed_url: {'status': status}})
    result = RSSCrawler(source).run(claimed(source.id))
    assert result.status == 'failed'
    assert [e['url'] for e in fetch_network.events() if e['kind'] == 'http'] == ['https://test.invalid/robots.txt', source.feed_url]
    db.session.remove()
    log = CrawlLog.query.one()
    assert (log.status, log.outcome, log.error_code) == ('failed', 'failed', code)
    state = db.session.get(CrawlSourceState, source.id)
    assert state.next_due_at - log.finished_at == timedelta(minutes=15)


def test_forbidden_source_is_blocked_for_a_day_with_attention(db, source, fetch_network):
    from app.models.crawl_runtime import CrawlSourceState
    fetch_network.configure(routes={source.feed_url: {'status': 403}})
    assert RSSCrawler(source).run(claimed(source.id)).errors == ['forbidden']
    db.session.remove()
    log, state = CrawlLog.query.one(), db.session.get(CrawlSourceState, source.id)
    assert (log.outcome, log.error_code, state.attention_reason) == ('blocked', 'forbidden', 'forbidden')
    assert state.next_due_at - log.finished_at == timedelta(hours=24)


def test_server_retry_after_sets_the_next_attempt(db, source, fetch_network):
    from app.models.crawl_runtime import CrawlSourceState
    fetch_network.configure(routes={source.feed_url: {'status': 429, 'headers': {'Retry-After': '3600'}}})
    RSSCrawler(source).run(claimed(source.id))
    db.session.remove()
    log, state = CrawlLog.query.one(), db.session.get(CrawlSourceState, source.id)
    assert state.next_due_at - log.finished_at == timedelta(hours=1)
