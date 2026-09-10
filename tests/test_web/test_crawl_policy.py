"""Persistent source permission through real admin pages, never a test-only API."""
import json
import hashlib
import io
import subprocess
from datetime import datetime

from werkzeug.datastructures import MultiDict

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.test_web import test_crawl_preview as preview_fixtures
from tests.test_web import test_crawl_evidence as evidence_fixtures

source = preview_fixtures.source
no_dispatch_or_model = preview_fixtures.no_dispatch_or_model
fetch_network = preview_fixtures.fetch_network
evidence_dir = evidence_fixtures.evidence_dir


def policy_page(client, source_id):
    response = client.get(f'/admin/sources/{source_id}/crawl-config')
    assert response.status_code == 200
    link = BeautifulSoup(response.text, 'html.parser').select_one('a[data-policy-link]')
    assert link is not None
    response = client.get(link['href'])
    assert response.status_code == 200
    return BeautifulSoup(response.text, 'html.parser')


def policy_form(client, source_id):
    form = policy_page(client, source_id).select_one('form[data-policy-save]')
    assert form is not None
    return form['action'], {item['name']: item.get('value', '') for item in form.select('input[name]')}


def save_policy(client, source_id, hosts='news.test.invalid', quality='news'):
    action, form = policy_form(client, source_id)
    form.update(allowed_hosts=hosts, quality_kind=quality)
    result = client.post(action, data=form)
    assert result.status_code == 302
    return result.location


def test_admin_saves_durable_policy_without_fetching_or_publishing(app, client, source, fetch_network):
    location = save_policy(client, source)
    with app.app_context():
        response = client.get(location)
        assert response.status_code == 200
        page = BeautifulSoup(response.text, 'html.parser')
        data = json.loads(page.select_one('[data-policy-document]').get_text())
        assert data['fetch_policy']['allowed_hosts'] == ['news.test.invalid']
        assert data['fetch_policy']['max_requests'] == 6
        assert data['quality_profile']['min_content_chars'] == 200
        assert data['quality_profile']['min_paragraphs'] == 2
        assert page.select_one('[data-policy-actor]').get_text(strip=True)
        assert page.select_one('[data-policy-created]').get_text(strip=True)
        listing = policy_page(client, source)
        assert listing.select_one(f'a[href="{location}"]')
        assert listing.select_one('[data-policy-state]').get_text(strip=True) == 'effective'
        assert 'No active recipe' in client.get(f'/admin/sources/{source}/crawl-config').text
        assert client.get('/api/v1/news').json['total'] == 0
    assert not fetch_network.processes


@pytest.mark.parametrize('field', ['recipe', 'status', 'created_by_id', 'document_hash', 'max_requests', 'evidence_path', 'generation'])
def test_policy_rejects_server_owned_controls(client, source, field):
    action, form = policy_form(client, source)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    form[field] = 'untrusted'
    assert client.post(action, data=form).status_code == 400
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'unconfigured'


@pytest.mark.parametrize('change', ['policy', 'source'])
def test_old_policy_form_cannot_overwrite_new_decision_or_source(client, source, csrf_token, change):
    action, form = policy_form(client, source)
    form.update(allowed_hosts='news.test.invalid', quality_kind='bulletin')
    if change == 'policy':
        save_policy(client, source, hosts='other.test.invalid')
    else:
        preview_fixtures.edit_source(client, source, csrf_token, url='https://changed.test.invalid/')
    response = client.post(action, data=form)
    assert response.status_code == 409
    page = policy_page(client, source)
    assert len(page.select('a[href*="/policies/"]')) == (1 if change == 'policy' else 0)


@pytest.mark.parametrize('change', ['url', 'url_aba', 'toggle_aba'])
def test_policy_needs_new_review_after_source_changes_even_if_restored(client, source, csrf_token, change):
    original = save_policy(client, source)
    if change == 'toggle_aba':
        for _ in range(2):
            assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    else:
        preview_fixtures.edit_source(client, source, csrf_token, url='https://changed.test.invalid/')
        if change == 'url_aba':
            preview_fixtures.edit_source(client, source, csrf_token)
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'stale'
    replacement = save_policy(client, source)
    assert replacement != original
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'effective'


def test_preview_uses_saved_policy_without_inline_permission(client, source, csrf_token, fetch_network):
    policy_url = save_policy(client, source, quality='bulletin')
    version = preview_fixtures.save_candidate(client, source, csrf_token)
    action, form = preview_fixtures.preview_form(client, version)
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview_fixtures.FEED, 'headers': {'Content-Type': 'application/rss+xml'},
    }})
    response = client.post(action, data=form)
    assert response.status_code == 302
    page = BeautifulSoup(client.get(response.location).text, 'html.parser')
    assert page.select_one('[data-preview-status]').get_text(strip=True) == 'ready'
    assert page.select_one('[data-field="title"]').get_text(strip=True) == 'Grenoble research'
    assert page.select_one(f'a[data-policy-reference][href="{policy_url}"]')
    assert '80 characters / 1 paragraphs' in page.get_text()
    assert 'name="allowed_hosts"' not in client.get(version).text
    assert client.get('/api/v1/news').json['total'] == 0


def revoke_form(client, source_id):
    form = policy_page(client, source_id).select_one('form[data-policy-revoke]')
    assert form is not None
    return form['action'], {item['name']: item.get('value', '') for item in form.select('input[name]')}


def captured_preview(client, source_id, csrf_token, fetch_network):
    version = preview_fixtures.save_candidate(client, source_id, csrf_token)
    action, form = preview_fixtures.preview_form(client, version)
    if 'expected_policy' not in form:
        form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    form['retain_evidence'] = '1'
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview_fixtures.FEED, 'headers': {'Content-Type': 'application/rss+xml'},
    }})
    result = client.post(action, data=form)
    assert result.status_code == 302
    return version, result.location


def test_revocation_blocks_new_previews_and_old_replay_until_new_grant(client, source, csrf_token, fetch_network, evidence_dir):
    first_policy = save_policy(client, source)
    version, report = captured_preview(client, source, csrf_token, fetch_network)
    original = BeautifulSoup(client.get(first_policy).text, 'html.parser').select_one('[data-policy-document]').get_text()
    action, form = revoke_form(client, source)
    revoked = client.post(action, data=form)
    assert revoked.status_code == 302
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'revoked'
    assert BeautifulSoup(client.get(first_policy).text, 'html.parser').select_one('[data-policy-document]').get_text() == original
    calls = len(fetch_network.processes)
    action, form = preview_fixtures.preview_form(client, version)
    assert client.post(action, data=form).status_code == 409
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 409
    assert BeautifulSoup(client.get(report).text, 'html.parser').select_one('[data-preview-status]').get_text(strip=True) == 'stale'
    assert len(fetch_network.processes) == calls
    assert save_policy(client, source) != first_policy
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 409
    _, fresh_report = captured_preview(client, source, csrf_token, fetch_network)
    assert client.post(fresh_report + '/replay', data={'csrf_token': csrf_token()}).status_code == 200


@pytest.mark.parametrize('damage', ['decision', 'marker', 'reverted_marker'])
def test_missing_latest_decision_never_restores_previous_grant(db, client, source, csrf_token, fetch_network, damage):
    original = save_policy(client, source)
    action, form = revoke_form(client, source)
    revoked = client.post(action, data=form)
    assert revoked.status_code == 302
    # External data-loss fault: public actions must not silently use an older grant.
    with db.engine.begin() as conn:
        if damage == 'decision':
            conn.execute(text('DELETE FROM crawl_policy_version WHERE id=:id'), {'id': int(revoked.location.rsplit('/', 1)[1])})
        else:
            conn.execute(text('UPDATE crawl_source_profile SET policy_generation=:generation WHERE source_id=:id'),
                         {'id': source, 'generation': None if damage == 'marker' else 1})
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'unavailable'
    assert BeautifulSoup(client.get(original).text, 'html.parser').select_one('[data-policy-state]').get_text(strip=True) != 'effective'
    version = preview_fixtures.save_candidate(client, source, csrf_token)
    action, form = preview_fixtures.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    assert client.post(action, data=form).status_code == 409
    assert not fetch_network.processes


@pytest.mark.parametrize('damage', ['checksum', 'stored_limits', 'missing_decision', 'report_reference'])
def test_policy_integrity_is_rechecked_on_report_get_and_replay(db, client, source, csrf_token, fetch_network, evidence_dir, damage):
    policy_url = save_policy(client, source)
    _, report = captured_preview(client, source, csrf_token, fetch_network)
    if damage == 'report_reference':
        evidence_fixtures.mutate_report(db, report, lambda data: data.update(source_policy='invalid-reference'))
    else:
        policy_id = int(policy_url.rsplit('/', 1)[1])
        with db.engine.begin() as conn:
            if damage == 'missing_decision':
                conn.execute(text('DELETE FROM crawl_policy_version WHERE id=:id'), {'id': policy_id})
            elif damage == 'checksum':
                conn.execute(text('UPDATE crawl_policy_version SET document_hash=:hash WHERE id=:id'), {'hash': '0' * 64, 'id': policy_id})
            else:
                value = json.loads(conn.execute(text('SELECT document FROM crawl_policy_version WHERE id=:id'), {'id': policy_id}).scalar_one())
                value['fetch_policy']['max_requests'] = 7
                encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
                conn.execute(text('UPDATE crawl_policy_version SET document=:data, document_hash=:hash WHERE id=:id'), {
                    'data': encoded, 'hash': hashlib.sha256(encoded.encode()).hexdigest(), 'id': policy_id,
                })
    before = len(fetch_network.processes)
    response = client.get(report)
    assert response.status_code == 200
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-preview-status]').get_text(strip=True) == 'stale'
    assert not page.select_one('form[data-replay]')
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 409
    assert len(fetch_network.processes) == before


@pytest.mark.parametrize('hosts,quality', [('', 'news'), ('127.0.0.1', 'news'), ('*.test.invalid', 'news'),
                                         ('https://news.test.invalid', 'news'), ('news.test.invalid:443', 'news'),
                                         ('news.test.invalid', 'custom'), ('x' * 4097, 'news'),
                                         ('\n'.join(f'n{i}.test.invalid' for i in range(17)), 'news')])
def test_policy_rejects_unsafe_or_unbounded_permission(client, source, hosts, quality):
    action, form = policy_form(client, source)
    form.update(allowed_hosts=hosts, quality_kind=quality)
    assert client.post(action, data=form).status_code == 400
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'unconfigured'


@pytest.mark.parametrize('bad_form', ['duplicate', 'upload', 'csrf'])
def test_policy_requires_unambiguous_csrf_protected_form(client, source, bad_form):
    action, form = policy_form(client, source)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    if bad_form == 'duplicate':
        form = MultiDict(list(form.items()) + [('allowed_hosts', 'other.test.invalid')])
    elif bad_form == 'upload':
        form['upload'] = (io.BytesIO(b'PRIVATE_UPLOAD'), 'data.txt')
    else:
        form.pop('csrf_token')
    assert client.post(action, data=form).status_code == 400
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'unconfigured'


@pytest.mark.parametrize('actor', ['anonymous', 'owner'])
def test_policy_history_save_and_revocation_keep_admin_protection(app, client, source, actor):
    location = save_policy(client, source)
    action, form = policy_form(client, source)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    revoke_action, revoke_data = revoke_form(client, source)
    probe = app.test_client()
    token = BeautifulSoup(probe.get('/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')['value']
    if actor == 'owner':
        assert probe.post('/auth/login', data={'csrf_token': token, 'email': 'owner@test.invalid', 'password': 'original-password'}).status_code == 302
    form['csrf_token'] = revoke_data['csrf_token'] = token
    for response in [probe.get(action), probe.get(location), probe.post(action, data=form), probe.post(revoke_action, data=revoke_data)]:
        assert response.status_code == 302
        assert ('/auth/login' in response.location) if actor == 'anonymous' else response.location == '/'
    assert len(policy_page(client, source).select('a[href*="/policies/"]')) == 1


def test_policy_cannot_be_overwritten_deleted_or_read_under_another_source(client, source, csrf_token):
    location = save_policy(client, source)
    original = BeautifulSoup(client.get(location).text, 'html.parser').select_one('[data-policy-document]').get_text()
    for method in ['post', 'put', 'delete']:
        assert getattr(client, method)(location, data={'csrf_token': csrf_token()}).status_code == 405
    assert client.post('/admin/sources/new', data={
        'name': 'Other source', 'slug': 'other-source', 'url': 'https://other.test.invalid/', 'category': 'national',
        'feed_type': 'rss', 'crawl_frequency_minutes': '60', 'is_active': 'on', 'csrf_token': csrf_token(),
    }).status_code == 302
    others = BeautifulSoup(client.get('/admin/sources').text, 'html.parser').select('a[href$="/edit"]')
    other_id = next(int(node['href'].split('/')[-2]) for node in others if int(node['href'].split('/')[-2]) != source)
    assert client.get(location.replace(f'/sources/{source}/', f'/sources/{other_id}/')).status_code == 404
    response = client.get(location)
    assert BeautifulSoup(response.text, 'html.parser').select_one('[data-policy-document]').get_text() == original
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    assert 'source-policy.v1' not in client.get('/api/v1/sources').text


def test_inactive_source_can_revoke_but_cannot_grant(client, source, csrf_token):
    assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    action, form = policy_form(client, source)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    assert client.post(action, data=form).status_code == 409
    action, form = revoke_form(client, source)
    assert client.post(action, data=form).status_code == 302
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'revoked'


def test_policy_history_shows_difference_without_changing_old_documents(client, source):
    original_url = save_policy(client, source, hosts='news.test.invalid\nold.test.invalid')
    old_doc = BeautifulSoup(client.get(original_url).text, 'html.parser').select_one('[data-policy-document]').get_text()
    new_url = save_policy(client, source, hosts='news.test.invalid\nnew.test.invalid', quality='bulletin')
    page = BeautifulSoup(client.get(new_url).text, 'html.parser')
    diff = page.select_one('[data-policy-diff]')
    assert diff is not None
    lines = diff.get_text().splitlines()
    assert any(line.startswith('-') and 'old.test.invalid' in line for line in lines)
    assert any(line.startswith('+') and 'new.test.invalid' in line for line in lines)
    assert any(line.startswith('+') and '"min_content_chars": 80' in line for line in lines)
    assert page.select_one(f'a[data-previous-policy][href="{original_url}"]')
    assert BeautifulSoup(client.get(original_url).text, 'html.parser').select_one('[data-policy-document]').get_text() == old_doc


@pytest.mark.parametrize('phase', ['during_preview', 'after_preview', 'during_replay'])
def test_policy_change_stales_inflight_results_and_stops_old_replay(app, client, source, csrf_token, fetch_network, evidence_dir, monkeypatch, phase):
    save_policy(client, source)
    original = subprocess.Popen
    changed = False

    def spawn(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            with app.app_context():
                action, form = revoke_form(client, source)
                assert client.post(action, data=form).status_code == 302
        return original(*args, **kwargs)

    if phase == 'during_preview':
        monkeypatch.setattr(subprocess, 'Popen', spawn)
    _, report = captured_preview(client, source, csrf_token, fetch_network)
    if phase == 'after_preview':
        action, form = revoke_form(client, source)
        assert client.post(action, data=form).status_code == 302
    before = len(fetch_network.events())
    if phase == 'during_replay':
        monkeypatch.setattr(subprocess, 'Popen', spawn)
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 409
    assert len(fetch_network.events()) == before
    assert BeautifulSoup(client.get(report).text, 'html.parser').select_one('[data-preview-status]').get_text(strip=True) == 'stale'
    assert client.get('/api/v1/news').json['total'] == 0


def test_display_frequency_and_crawl_updates_do_not_revoke_policy(db, client, source, csrf_token):
    save_policy(client, source)
    _, old_form = policy_form(client, source)
    preview_fixtures.edit_source(client, source, csrf_token, name='Renamed source', crawl_frequency_minutes='240')
    with db.engine.begin() as conn:
        conn.execute(text('UPDATE news_source SET last_crawled_at=:now, updated_at=:now WHERE id=:id'),
                     {'now': datetime(2026, 9, 9, 12, 30), 'id': source})
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'effective'
    _, fresh_form = policy_form(client, source)
    assert fresh_form['expected_generation'] == old_form['expected_generation']
    assert fresh_form['expected_source'] == old_form['expected_source']


def test_policy_race_rechecks_generation_at_write_boundary(db, app, client, source, monkeypatch):
    save_policy(client, source)
    action, form = policy_form(client, source)
    form.update(allowed_hosts='loser.test.invalid', quality_kind='bulletin')
    competed = False

    def competitor(conn, cursor, statement, parameters, context, executemany):
        nonlocal competed
        if not competed and statement.upper().startswith('UPDATE CRAWL_SOURCE_PROFILE'):
            competed = True
            with app.app_context():
                save_policy(client, source, hosts='winner.test.invalid')

    event.listen(db.engine, 'before_cursor_execute', competitor)
    try:
        assert client.post(action, data=form).status_code == 409
    finally:
        event.remove(db.engine, 'before_cursor_execute', competitor)
    assert competed
    page = policy_page(client, source)
    history = page.select('a[href*="/policies/"]')
    assert len(history) == 2
    assert 'winner.test.invalid' in client.get(history[0]['href']).text


@pytest.mark.parametrize('revoke', [False, True])
def test_failed_policy_write_preserves_previous_permission_and_private_error(db, client, source, caplog, revoke):
    save_policy(client, source)
    action, form = revoke_form(client, source) if revoke else policy_form(client, source)
    if not revoke:
        form.update(allowed_hosts='other.test.invalid', quality_kind='bulletin')
    with db.engine.begin() as conn:
        conn.execute(text("CREATE TRIGGER fail_policy BEFORE INSERT ON crawl_policy_version BEGIN SELECT RAISE(FAIL, 'PRIVATE_POLICY_SQL'); END"))
    response = client.post(action, data=form)
    assert response.status_code == 503
    assert 'PRIVATE_POLICY_SQL' not in response.text + caplog.text
    assert 'other.test.invalid' not in caplog.text
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'effective'
    with db.engine.begin() as conn:
        conn.execute(text('DROP TRIGGER fail_policy'))
    assert client.post(action, data=form).status_code == 302
    assert len(policy_page(client, source).select('a[href*="/policies/"]')) == 2


def test_successful_policy_redirect_needs_no_post_commit_database_read(db, client, source):
    action, form = policy_form(client, source)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    committed = False

    def after_commit(session):
        nonlocal committed
        committed = True

    def reject_read(conn, cursor, statement, parameters, context, executemany):
        if committed and statement.lstrip().upper().startswith('SELECT'):
            raise OperationalError('synthetic disconnect after commit', {}, Exception('offline'))

    event.listen(Session, 'after_commit', after_commit)
    event.listen(db.engine, 'before_cursor_execute', reject_read)
    try:
        response = client.post(action, data=form)
        assert response.status_code == 302
    finally:
        event.remove(Session, 'after_commit', after_commit)
        event.remove(db.engine, 'before_cursor_execute', reject_read)
    assert committed
    assert client.get(response.location).status_code == 200


@pytest.mark.parametrize('count', [1, 16])
def test_encoded_policy_limit_is_checked_before_any_state_change(client, source, count):
    action, form = policy_form(client, source)
    form.update(allowed_hosts='\n'.join(f'n{i}.' + 'é.' * 100 + 'test.invalid' for i in range(count)), quality_kind='news')
    assert client.post(action, data=form).status_code == 400
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'unconfigured'
    assert save_policy(client, source)


@pytest.mark.parametrize('override', ['allowed_hosts', 'quality_kind', 'expected_policy'])
def test_saved_policy_cannot_be_overridden_inline(client, source, csrf_token, fetch_network, override):
    save_policy(client, source)
    version = preview_fixtures.save_candidate(client, source, csrf_token)
    action, form = preview_fixtures.preview_form(client, version)
    form[override] = '999' if override == 'expected_policy' else 'untrusted'
    assert client.post(action, data=form).status_code == (409 if override == 'expected_policy' else 400)
    assert not fetch_network.processes


def test_saved_host_policy_reaches_real_engine_gate(client, source, csrf_token, fetch_network):
    save_policy(client, source, hosts='other.test.invalid')
    version = preview_fixtures.save_candidate(client, source, csrf_token)
    action, form = preview_fixtures.preview_form(client, version)
    result = client.post(action, data=form)
    assert result.status_code == 302
    assert BeautifulSoup(client.get(result.location).text, 'html.parser').select_one('[data-preview-status]').get_text(strip=True) == 'blocked'
    assert not fetch_network.processes


def test_saved_quality_standard_changes_real_extraction_level(client, source, csrf_token, fetch_network):
    recipe = preview_fixtures.recipe_for(source)
    recipe['feed']['fields']['content'] = 'content'
    version = preview_fixtures.save_candidate(client, source, csrf_token, recipe)
    body = 'Research Grenoble announces a new sensor for industrial laboratories. The team shares the first measurements with local partners.'
    feed = f'<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>News</title><item><title>Research Grenoble</title><link>https://news.test.invalid/research</link><content:encoded><![CDATA[<p>{body}</p>]]></content:encoded></item></channel></rss>'
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'body': feed, 'headers': {'Content-Type': 'application/rss+xml'}}})
    reports = []
    for kind, level in [('news', 'excerpt'), ('bulletin', 'full')]:
        save_policy(client, source, quality=kind)
        action, form = preview_fixtures.preview_form(client, version)
        result = client.post(action, data=form)
        assert result.status_code == 302
        page = BeautifulSoup(client.get(result.location).text, 'html.parser')
        assert page.select_one('[data-field="content_level"]').get_text(strip=True) == level
        reports.append(result.location)
    old = BeautifulSoup(client.get(reports[0]).text, 'html.parser')
    assert old.select_one('[data-field="content_level"]').get_text(strip=True) == 'excerpt'
    assert old.select_one('[data-preview-status]').get_text(strip=True) == 'stale'


@pytest.mark.parametrize('decision', ['grant', 'revoke'])
def test_establishing_policy_invalidates_single_use_permission_and_replay(client, source, csrf_token, fetch_network, evidence_dir, decision):
    version, report = captured_preview(client, source, csrf_token, fetch_network)
    action, form = preview_fixtures.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    if decision == 'grant':
        save_policy(client, source)
    else:
        revoke_action, data = revoke_form(client, source)
        assert client.post(revoke_action, data=data).status_code == 302
    before = len(fetch_network.processes)
    assert client.post(action, data=form).status_code == 409
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 409
    assert len(fetch_network.processes) == before


def test_recent_history_is_bounded_without_deleting_audit(client, source):
    first = save_policy(client, source)
    for _ in range(50):
        save_policy(client, source)
    assert len(policy_page(client, source).select('a[href*="/policies/"]')) == 50
    assert client.get(first).status_code == 200


@pytest.mark.parametrize('problem', ['csrf', 'extra_field', 'duplicate', 'upload'])
def test_revocation_form_is_strict(client, source, problem):
    save_policy(client, source)
    action, form = revoke_form(client, source)
    if problem == 'csrf':
        form.pop('csrf_token')
    elif problem == 'extra_field':
        form['quality_kind'] = 'bulletin'
    elif problem == 'duplicate':
        form = MultiDict(list(form.items()) + [('expected_generation', '999')])
    else:
        form['upload'] = (io.BytesIO(b'PRIVATE_UPLOAD'), 'data.txt')
    assert client.post(action, data=form).status_code == 400
    assert policy_page(client, source).select_one('[data-policy-state]').get_text(strip=True) == 'effective'
