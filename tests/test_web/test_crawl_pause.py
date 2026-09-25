"""Pausing a source stops scheduling without invalidating its policy or approved recipe."""
import pytest
from bs4 import BeautifulSoup

from app.crawlers.rss_crawler import RSSCrawler
from app.models.crawl_runtime import CrawlSourceState
from app.models.source import NewsSource
from tests.support.runs import claimed
from tests.test_web import test_crawl_activation as activation
from tests.test_web import test_crawl_policy as policy
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_routing as routing

source = preview.source
fetch_network = preview.fetch_network
sent = routing.sent


def click(client, source_id, kind):
    page = BeautifulSoup(client.get('/admin/sources').text, 'html.parser')
    form = page.select_one(f'form[data-{kind}][action="/admin/sources/{source_id}/{kind}"]')
    assert form is not None, f'no {kind} button for source {source_id}'
    fields = {item['name']: item.get('value', '') for item in form.select('input[name]')}
    return client.post(form['action'], data=fields, follow_redirects=True)


def test_paused_sources_are_skipped_until_resumed(db, client, source, sent):
    from app.crawlers.tasks import dispatch_due_crawls
    assert 'paused' in click(client, source, 'pause').text
    assert dispatch_due_crawls.run() == {'dispatched': 0}
    page = BeautifulSoup(client.get('/admin/sources').text, 'html.parser')
    assert page.select_one('[data-paused]').get_text(strip=True) == 'Paused'
    assert click(client, source, 'resume').status_code == 200
    assert BeautifulSoup(client.get('/admin/sources').text, 'html.parser').select_one('[data-paused]') is None
    assert dispatch_due_crawls.run() == {'dispatched': 1}


def test_pause_and_resume_keep_the_approved_recipe_and_policy(db, client, source, csrf_token, fetch_network, sent):
    activation.approved(client, source, csrf_token, fetch_network)
    click(client, source, 'pause')
    click(client, source, 'resume')
    index = BeautifulSoup(client.get(f'/admin/sources/{source}/crawl-config').text, 'html.parser')
    assert index.select_one('[data-activation-generation]').get_text(strip=True) == '1'
    assert index.select_one('[data-active-version]') is not None
    assert policy.policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'effective'
    log = routing.scheduled_run(db, sent)
    assert (log.route, log.outcome) == ('schema', 'success')


def test_crawl_now_on_a_paused_source_explains_it_and_queues_nothing(db, client, source, csrf_token):
    click(client, source, 'pause')
    before = db.session.get(CrawlSourceState, source).next_due_at
    page = client.post(f'/admin/sources/{source}/crawl-now', data={'csrf_token': csrf_token()}, follow_redirects=True).text
    assert 'is paused' in page
    db.session.remove()
    state = db.session.get(CrawlSourceState, source)
    assert state.next_due_at == before and state.due_reason != 'manual'


def test_a_run_in_progress_finishes_and_the_source_stays_paused(db, client, source, fetch_network, sent):
    claim = claimed(source)
    click(client, source, 'pause')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    assert RSSCrawler(db.session.get(NewsSource, source)).run(claim).status == 'success'
    db.session.remove()
    assert db.session.get(CrawlSourceState, source).paused_at is not None


@pytest.mark.parametrize('kind', ['pause', 'resume'])
def test_pause_controls_require_csrf(client, source, kind):
    assert client.post(f'/admin/sources/{source}/{kind}', data={}).status_code == 400
