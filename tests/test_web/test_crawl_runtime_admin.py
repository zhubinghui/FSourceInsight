"""Operator-visible runtime: routes, due times, attention, manual requests and the beat switch."""
from bs4 import BeautifulSoup

from app.crawlers.fetcher import FetchError
from app.models.crawl_runtime import CrawlSourceState
from app.models.source import NewsSource
from tests.support.runs import claimed
from tests.test_crawlers.test_crawl_runs import FixtureCrawler
from tests.test_web import test_crawl_preview as preview

source = preview.source


def test_source_list_shows_route_next_due_and_attention(db, client, source):
    FixtureCrawler(db.session.get(NewsSource, source), error=FetchError('robots_unavailable')).run(claimed(source))
    page = BeautifulSoup(client.get('/admin/sources').text, 'html.parser')
    row = page.select_one('[data-route]').find_parent('tr')
    assert row.select_one('[data-route]').get_text(strip=True) == 'Legacy'
    assert row.select_one('[data-next-due]').get_text(strip=True)
    assert row.select_one('[data-attention]').get_text(strip=True) == 'robots_unavailable'
    logs = BeautifulSoup(client.get('/admin/crawl-logs').text, 'html.parser')
    assert logs.select_one('[data-log-route]').get_text(strip=True) == 'legacy'
    assert logs.select_one('[data-log-outcome]').get_text(strip=True) == 'blocked'
    assert logs.select_one('[data-log-error]').get_text(strip=True) == 'robots_unavailable'


def test_crawl_now_reports_running_and_disabled_sources(db, client, source, csrf_token):
    path = f'/admin/sources/{source}/crawl-now'
    page = client.post(path, data={'csrf_token': csrf_token()}, follow_redirects=True).text
    assert 'starts within a minute' in page
    db.session.remove()
    assert db.session.get(CrawlSourceState, source).due_reason == 'manual'
    claimed(source)
    assert 'already running' in client.post(path, data={'csrf_token': csrf_token()}, follow_redirects=True).text
    assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    assert 'disabled' in client.post(path, data={'csrf_token': csrf_token()}, follow_redirects=True).text


def test_settings_no_longer_offer_the_retired_check_interval(client, source):
    page = client.get('/admin/settings').text
    assert 'crawl_check_interval_hours' not in page
    assert 'crawl_daily_hour' in page


def test_beat_runs_the_dispatcher_and_retired_tasks_are_harmless(db, source, monkeypatch):
    from celery_app import celery
    from app.crawlers import tasks
    schedule = celery.conf.beat_schedule
    assert schedule['dispatch-due-crawls']['task'] == 'app.crawlers.tasks.dispatch_due_crawls'
    assert schedule['recover-article-llm']['task'] == 'app.llm.article_tasks.recover'
    assert 'daily-crawl-all' not in schedule and 'crawl-frequency-check' not in schedule
    sent = []
    monkeypatch.setattr('celery.app.base.Celery.send_task', lambda self, *a, **k: sent.append(a))
    assert tasks.crawl_all_sources.run()['skipped'] is True
    assert tasks.schedule_due_crawls.run()['skipped'] is True
    assert sent == []
