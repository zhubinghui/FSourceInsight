"""Capture history controls and database failure boundaries via Admin HTTP."""
import json

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.test_web import test_crawl_capture as captures
from tests.test_web import test_crawl_policy as policies
from tests.test_web import test_crawl_preview as previews

source = captures.source
fetch_network = captures.fetch_network
no_dispatch_or_model = captures.no_dispatch_or_model
evidence_dir = captures.evidence_dir
take_preview = captures.take_preview
capture_page = captures.capture_page
history_page = captures.history_page


def test_policy_and_quality_fingerprints_remain_historical(client, source, csrf_token, fetch_network):
    policy = policies.save_policy(client, source, hosts='other.test.invalid', quality='news')
    version, report = take_preview(client, source, csrf_token, fetch_network)
    location, _, page = capture_page(client, report)
    first = json.loads(page.select_one('[data-capture-document]').get_text())
    assert first['source_policy']['id'] == int(policy.rsplit('/', 1)[1])
    assert len(first['fetch_policy_hash']) == len(first['quality_profile_hash']) == 64
    policies.save_policy(client, source, hosts='other.test.invalid', quality='bulletin')
    _, second_report = take_preview(client, source, csrf_token, fetch_network, version=version)
    second = json.loads(capture_page(client, second_report)[2].select_one('[data-capture-document]').get_text())
    assert second['fetch_policy_hash'] == first['fetch_policy_hash']
    assert second['quality_profile_hash'] != first['quality_profile_hash']
    assert json.loads(BeautifulSoup(client.get(location).text, 'html.parser').select_one('[data-capture-document]').get_text()) == first
    assert history_page(client, source)[2].select_one('[data-capture-generation]').get_text(strip=True) == '2'


def test_legacy_history_never_becomes_complete_by_collecting_new_samples(db, client, source, csrf_token, fetch_network):
    version = previews.save_candidate(client, source, csrf_token)
    db.session.execute(text('UPDATE crawl_source_profile SET capture_history_complete=0'))
    db.session.commit()
    for _ in range(2):
        take_preview(client, source, csrf_token, fetch_network, version=version, hosts='other.test.invalid')
    page = history_page(client, source)[2]
    assert page.select_one('[data-capture-history-state]').get_text(strip=True) == 'incomplete'
    assert page.select_one('[data-capture-generation]').get_text(strip=True) == '2'
    assert len(page.select('a[data-capture-entry]')) == 2


def test_capture_history_limits_display_without_deleting_old_entries(client, source, csrf_token, fetch_network):
    version, report = take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    first_capture = capture_page(client, report)[0]
    for _ in range(50):
        take_preview(client, source, csrf_token, fetch_network, version=version, hosts='other.test.invalid')
    assert len(history_page(client, source)[2].select('a[data-capture-entry]')) == 50
    assert client.get(first_capture).status_code == 200


@pytest.mark.parametrize('actor', ['anonymous', 'owner'])
def test_capture_pages_keep_admin_protection(app, client, source, csrf_token, fetch_network, actor):
    _, report = take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    detail = capture_page(client, report)[0]
    listing = history_page(client, source)[0]
    probe = app.test_client() if actor == 'anonymous' else client
    if actor == 'owner':
        assert client.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password',
                                               'csrf_token': csrf_token()}).status_code == 302
    for path in (detail, listing):
        response = probe.get(path)
        assert response.status_code == 302
        assert ('/auth/login' in response.location) if actor == 'anonymous' else response.location == '/'
        assert 'data-capture-document' not in response.text


def test_capture_is_source_scoped_read_only_and_private(client, source, csrf_token, fetch_network):
    _, report = take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    location, response, _ = capture_page(client, report)
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    for method in ('post', 'put', 'delete'):
        assert getattr(client, method)(location, data={'csrf_token': csrf_token()}).status_code == 405
    result = client.post('/admin/sources/new', data={'name': 'Other', 'slug': 'other',
        'url': 'https://other.test.invalid/', 'feed_type': 'rss', 'category': 'national', 'csrf_token': csrf_token()})
    assert result.status_code == 302
    rows = BeautifulSoup(client.get('/admin/sources').text, 'html.parser').select('tbody tr')
    row = next(row for row in rows if row.select_one('a[href="https://other.test.invalid/"]'))
    other = row.select_one('a[href$="/edit"]')['href'].split('/')[-2]
    assert client.get(location.replace(f'/sources/{source}/', f'/sources/{other}/')).status_code == 404
    assert history_page(client, other)[2].select_one('[data-capture-history-state]').get_text(strip=True) == 'unconfigured'
    assert client.get('/api/v1/news').json['total'] == 0


@pytest.mark.parametrize('stage', ['manifest', 'marker', 'reference', 'commit'])
def test_capture_storage_failure_is_atomic_including_report_pruning(db, client, source, csrf_token, fetch_network, caplog, stage):
    version, first = take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    for _ in range(19):
        take_preview(client, source, csrf_token, fetch_network, version=version, hosts='other.test.invalid')
    action, form = previews.preview_form(client, version)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    failed = []

    def reject(*args):
        if stage == 'commit' or args[2].startswith({'manifest': 'INSERT INTO crawl_capture_manifest',
                'marker': 'UPDATE crawl_source_profile SET capture_generation', 'reference': 'UPDATE crawl_preview_report'}[stage]):
            failed.append(True)
            raise OperationalError('PRIVATE_CAPTURE_SQL', {}, Exception('private'))

    target, hook = (Session, 'before_commit') if stage == 'commit' else (db.engine, 'before_cursor_execute')
    event.listen(target, hook, reject)
    try:
        response = client.post(action, data=form)
        assert response.status_code == 503
    finally:
        event.remove(target, hook, reject)
    assert failed
    assert 'PRIVATE_CAPTURE_SQL' not in response.text + caplog.text
    assert client.get(first).status_code == 200
    page = history_page(client, source)[2]
    assert page.select_one('[data-capture-generation]').get_text(strip=True) == '20'
    assert len(page.select('a[data-capture-entry]')) == 20
    assert page.select_one('[data-capture-history-state]').get_text(strip=True) == 'tracked'
    assert client.post(action, data=form).status_code == 302
    assert client.get(first).status_code == 404


def test_capture_success_does_not_read_database_after_commit(db, client, source, csrf_token, fetch_network):
    version = previews.save_candidate(client, source, csrf_token)
    action, form = previews.preview_form(client, version)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    committed = []

    def committed_now(session):
        committed.append(True)

    def fail_read(conn, cursor, statement, parameters, context, executemany):
        if committed and statement.lstrip().upper().startswith('SELECT'):
            raise OperationalError('disconnect after commit', {}, Exception('offline'))

    event.listen(Session, 'after_commit', committed_now)
    event.listen(db.engine, 'before_cursor_execute', fail_read)
    try:
        response = client.post(action, data=form)
        assert response.status_code == 302
    finally:
        event.remove(Session, 'after_commit', committed_now)
        event.remove(db.engine, 'before_cursor_execute', fail_read)
    assert committed
    assert capture_page(client, response.location)
