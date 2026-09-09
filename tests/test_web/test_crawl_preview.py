"""Preview through real admin HTTP; external network runs only synthetic bootstrap."""
import json
import pytest
import subprocess

from bs4 import BeautifulSoup

from tests.test_crawlers import conftest as network_fixtures
from tests.test_web import test_crawl_config as candidate_fixtures

fetch_network = network_fixtures.fetch_network
source = candidate_fixtures.source
no_dispatch_or_model = candidate_fixtures.no_dispatch_or_model
recipe_for = candidate_fixtures.recipe_for


FEED = '''<rss version="2.0"><channel><title>News</title><item>
<guid isPermaLink="false">research-1</guid><title>Grenoble research</title>
<link>https://news.test.invalid/research</link>
<description>Grenoble laboratory reports a new sensor.</description>
<pubDate>Tue, 08 Sep 2026 08:00:00 GMT</pubDate>
</item></channel></rss>'''


def save_candidate(client, source_id, csrf_token, recipe=None):
    document = recipe or recipe_for(source_id)
    response = client.post(f'/admin/sources/{source_id}/crawl-config', data={
        'recipe': json.dumps(document), 'csrf_token': csrf_token(),
    })
    assert response.status_code == 302
    return response.location


def preview_form(client, version_url):
    page = BeautifulSoup(client.get(version_url).text, 'html.parser')
    form = page.select_one('form[data-preview]')
    assert form is not None
    return form['action'], {field['name']: field.get('value', '') for field in form.select('input[name]')
                           if not field.has_attr('disabled') and (field.get('type') != 'checkbox' or field.has_attr('checked'))}


def edit_source(client, source_id, csrf_token, **changes):
    data = {
        'name': 'Candidate source', 'slug': 'candidate-source', 'url': 'https://news.test.invalid/',
        'feed_url': 'https://news.test.invalid/feed', 'feed_type': 'rss', 'category': 'national',
        'crawl_frequency_minutes': '60', 'is_active': 'on', 'csrf_token': csrf_token(),
    }
    data.update(changes)
    assert client.post(f'/admin/sources/{source_id}/edit', data=data).status_code == 302


def test_admin_can_preview_and_reopen_samples_without_ingestion(app, client, source, csrf_token, fetch_network):
    recipe = recipe_for(source)
    recipe['feed']['fields'].update(content='summary', published_at='published')
    version_url = save_candidate(client, source, csrf_token, recipe)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': FEED, 'headers': {'Content-Type': 'application/rss+xml'},
    }})
    response = client.post(action, data=form)
    assert response.status_code == 302
    assert fetch_network.processes
    requests = len(fetch_network.events())
    with app.app_context():
        report = client.get(response.location)
        assert report.status_code == 200
        page = BeautifulSoup(report.text, 'html.parser')
        assert page.select_one('[data-preview-status]').get_text(strip=True) == 'ready'
        assert page.select_one('[data-count="valid"]').get_text(strip=True) == '1'
        sample = page.select_one('[data-sample]')
        assert sample.select_one('[data-field="title"]').get_text(strip=True) == 'Grenoble research'
        assert sample.select_one('a[data-original]')['href'] == 'https://news.test.invalid/research'
        assert sample.select_one('[data-field="content_level"]').get_text(strip=True) == 'excerpt'
        assert sample.select_one('[data-field="source_language"]').get_text(strip=True) == 'en'
        assert '2026-09-08T08:00:00+00:00' in sample.get_text()
        assert 'Grenoble laboratory reports a new sensor.' in sample.get_text()
        assert client.get('/api/v1/news').json['total'] == 0
        version = BeautifulSoup(client.get(version_url).text, 'html.parser')
        assert version.select_one('[data-version-status]').get_text(strip=True) == 'Candidate'
        assert version.select_one(f'a[href="{response.location}"]')
        assert 'No raw snapshots retained' in report.text
    assert len(fetch_network.events()) == requests


@pytest.mark.parametrize('field', ['max_requests', 'recipe', 'status', 'snapshots', 'quality_report', 'created_by_id'])
def test_preview_rejects_injected_controls_before_network(client, source, csrf_token, fetch_network, field):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    form[field] = 'untrusted'
    response = client.post(action, data=form)
    assert response.status_code == 400
    assert not fetch_network.processes


@pytest.mark.parametrize('change', ['generation', 'source', 'inactive'])
def test_preview_checks_current_inputs_before_network(client, source, csrf_token, fetch_network, change):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    if change == 'generation':
        form['expected_generation'] = '99'
    elif change == 'source':
        form['expected_source'] = '0' * 64
    else:
        assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    assert client.post(action, data=form).status_code == 409
    assert not fetch_network.processes


def test_samples_are_bounded_and_escaped(client, source, csrf_token, fetch_network, caplog):
    recipe = recipe_for(source)
    recipe['feed']['fields']['content'] = 'summary'
    version_url = save_candidate(client, source, csrf_token, recipe)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    body = '&lt;svg onload=alert(1)&gt;&lt;/svg&gt;' + 'Grenoble research ' * 100 + 'RAW_PRIVATE_TAIL'
    items = ''.join(f'<item><title>Research {i}</title><link>https://news.test.invalid/{i}</link><description>{body}</description></item>' for i in range(8))
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': f'<rss version="2.0"><channel><title>News</title>{items}</channel></rss>',
        'headers': {'Content-Type': 'application/rss+xml'},
    }})
    saved = client.post(action, data=form)
    assert saved.status_code == 302
    response = client.get(saved.location)
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-count="valid"]').get_text(strip=True) == '8'
    assert len(page.select('[data-sample]')) == 5
    assert all(len(node.get_text()) <= 1000 for node in page.select('[data-field="content"]'))
    assert 'RAW_PRIVATE_TAIL' not in response.text + caplog.text
    assert not page.select('[onload], [onerror]')
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Referrer-Policy'] == 'no-referrer'
    assert all(node['rel'] == ['noopener', 'noreferrer'] for node in page.select('a[data-original]'))


def test_only_twenty_reports_per_candidate_are_retained(app, client, source, csrf_token, fetch_network):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    # Valid permission, but intentionally not for the recipe's host: zero HTTP.
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    locations = []
    for _ in range(21):
        result = client.post(action, data=form)
        assert result.status_code == 302
        locations.append(result.location)
    with app.app_context():
        assert client.get(locations[0]).status_code == 404
        assert client.get(locations[-1]).status_code == 200
        assert len(BeautifulSoup(client.get(version_url).text, 'html.parser').select('a[href*="/previews/"]')) == 20
    assert not fetch_network.processes


@pytest.mark.parametrize('hosts,kind', [('', 'news'), ('127.0.0.1', 'news'), ('*.test.invalid', 'news'),
    ('https://news.test.invalid/', 'news'), ('news.test.invalid:443', 'news'),
    ('news.test.invalid', 'custom'), ('news.test.invalid\n' * 17, 'news')])
def test_preview_requires_an_explicit_valid_policy(client, source, csrf_token, fetch_network, hosts, kind):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts=hosts, quality_kind=kind)
    assert client.post(action, data=form).status_code == 400
    assert not fetch_network.processes


@pytest.mark.parametrize('actor', ['anonymous', 'owner', 'no_csrf'])
def test_preview_and_report_keep_admin_protection(app, client, source, csrf_token, fetch_network, actor):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    saved = client.post(action, data=form)
    assert saved.status_code == 302
    if actor == 'anonymous':
        probe = app.test_client()
        form['csrf_token'] = BeautifulSoup(probe.get('/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')['value']
    else:
        probe = client
        if actor == 'owner':
            assert client.post('/auth/login', data={'email': 'owner@test.invalid',
                'password': 'original-password', 'csrf_token': csrf_token()}).status_code == 302
            form['csrf_token'] = csrf_token()
        else:
            form.pop('csrf_token')
    response = probe.post(action, data=form)
    assert response.status_code == (400 if actor == 'no_csrf' else 302)
    if actor != 'no_csrf':
        assert probe.get(saved.location).status_code == 302
        assert ('/auth/login' in response.location) if actor == 'anonymous' else response.location == '/'
    assert not fetch_network.processes


def test_unexpected_execution_error_is_fixed_and_does_not_save_report(client, source, csrf_token, fetch_network, monkeypatch, caplog):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')

    def broken_process(*args, **kwargs):
        raise RuntimeError('DO_NOT_LOG_PREVIEW_BODY')

    monkeypatch.setattr(subprocess, 'Popen', broken_process)
    response = client.post(action, data=form)
    assert response.status_code == 503
    assert 'DO_NOT_LOG_PREVIEW_BODY' not in response.text + caplog.text
    assert not BeautifulSoup(client.get(version_url).text, 'html.parser').select('a[href*="/previews/"]')


@pytest.mark.parametrize('case,status,error', [
    ('forbidden', 'blocked', 'forbidden'), ('empty_html', 'inconclusive', 'no_evidence'),
    ('partial', 'partial', 'missing_fields'), ('empty_feed', 'no_change', None),
    ('bad_feed', 'failed', 'invalid_article'),
])
def test_real_engine_status_is_not_replaced_with_success(client, source, csrf_token, fetch_network, case, status, error):
    recipe = recipe_for(source)
    url = 'https://news.test.invalid/feed'
    route = {'body': '<rss version="2.0"><channel><title>Quiet</title></channel></rss>', 'headers': {'Content-Type': 'application/rss+xml'}}
    if case in {'partial', 'empty_html'}:
        recipe.pop('feed')
        recipe['extractor'] = 'html'
        recipe['list_pages'] = [{'url': url, 'item_selector': 'article', 'fields': {
            'title': {'selector': 'h2', 'read': 'text'}, 'url': {'selector': 'a', 'read': 'attr', 'attr': 'href'},
        }}]
        route = {'body': '<html></html>' if case == 'empty_html' else '<article><h2>Research</h2><a href="/one">Read</a></article><article><h2>Missing link</h2></article>'}
    elif case == 'forbidden':
        route = {'status': 403}
    elif case == 'bad_feed':
        route['body'] = '<html>Not a feed</html>'
    version_url = save_candidate(client, source, csrf_token, recipe)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    fetch_network.configure(routes={url: route})
    saved = client.post(action, data=form)
    assert saved.status_code == 302
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert page.select_one('[data-preview-status]').get_text(strip=True) == status
    if error:
        assert error in ' '.join(node.get_text() for node in page.select('[data-error]'))
    assert client.get('/api/v1/news').json['total'] == 0


def test_quality_choice_is_independent_and_previous_report_does_not_change(client, source, csrf_token, fetch_network):
    recipe = recipe_for(source)
    recipe['feed']['fields']['content'] = 'content'
    version_url = save_candidate(client, source, csrf_token, recipe)
    body = 'Research Grenoble announces a new sensor for industrial laboratories. The team shares the first measurements with local partners.'
    feed = f'<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>News</title><item><title>Research Grenoble</title><link>https://news.test.invalid/research</link><content:encoded><![CDATA[<p>{body}</p>]]></content:encoded></item></channel></rss>'
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'body': feed, 'headers': {'Content-Type': 'application/rss+xml'}}})
    reports = []
    for kind in ['news', 'bulletin']:
        action, form = preview_form(client, version_url)
        form.update(allowed_hosts='news.test.invalid', quality_kind=kind)
        saved = client.post(action, data=form)
        assert saved.status_code == 302
        reports.append(saved.location)
    for location, level in zip(reports, ['excerpt', 'full']):
        page = BeautifulSoup(client.get(location).text, 'html.parser')
        assert page.select_one('[data-field="content_level"]').get_text(strip=True) == level


def test_operational_or_display_updates_do_not_stale_report(app, db, client, source, csrf_token, fetch_network):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    saved = client.post(action, data=form)
    edit_source(client, source, csrf_token, name='Renamed source', crawl_frequency_minutes='15')
    from sqlalchemy import text
    with db.engine.begin() as conn:
        conn.execute(text('UPDATE news_source SET last_crawled_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=:id'), {'id': source})
    with app.app_context():
        page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
        assert page.select_one('[data-preview-status]').get_text(strip=True) == 'blocked'
    assert not fetch_network.processes


def test_report_storage_failure_rolls_back_and_is_private(app, db, client, source, csrf_token, fetch_network, caplog):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    with db.engine.begin() as conn:
        conn.exec_driver_sql("""CREATE TRIGGER reject_preview BEFORE INSERT ON crawl_preview_report
            BEGIN SELECT RAISE(FAIL, 'PRIVATE_PREVIEW_SQL'); END""")
    response = client.post(action, data=form)
    assert response.status_code == 503
    assert 'PRIVATE_PREVIEW_SQL' not in response.text + caplog.text
    with app.app_context():
        assert not BeautifulSoup(client.get(version_url).text, 'html.parser').select('a[href*="/previews/"]')
        assert client.get('/api/v1/news').json['total'] == 0
    with db.engine.begin() as conn:
        conn.exec_driver_sql('DROP TRIGGER reject_preview')
    assert client.post(action, data=form).status_code == 302


def test_report_is_bound_to_source_and_candidate(client, source, csrf_token, fetch_network):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='other.test.invalid', quality_kind='news')
    saved = client.post(action, data=form)
    assert saved.status_code == 302
    second = save_candidate(client, source, csrf_token)
    assert client.get(saved.location.replace(version_url, second)).status_code == 404
    created = client.post('/admin/sources/new', data={'name': 'Other', 'slug': 'other',
        'url': 'https://other.test.invalid/', 'feed_type': 'rss', 'category': 'national', 'csrf_token': csrf_token()})
    assert created.status_code == 302
    rows = BeautifulSoup(client.get('/admin/sources').text, 'html.parser').select('tbody tr')
    row = next(row for row in rows if row.select_one('a[href="https://other.test.invalid/"]'))
    other_id = row.select_one('a[href$="/edit"]')['href'].split('/')[-2]
    assert client.get(saved.location.replace(f'/sources/{source}/', f'/sources/{other_id}/')).status_code == 404
    assert client.post(action.replace(f'/sources/{source}/', f'/sources/{other_id}/'), data=form).status_code == 404
    assert client.get(saved.location).status_code == 200
    assert not fetch_network.processes


@pytest.mark.parametrize('when', ['during', 'after'])
def test_report_is_stale_if_source_changes(app, client, source, csrf_token, fetch_network, monkeypatch, when):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'body': FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    original = subprocess.Popen
    changed = []

    def spawn(command, **kwargs):
        if when == 'during' and not changed:
            changed.append(True)
            # Another HTTP request at the external process boundary: no engine mocks.
            with app.app_context():
                edit_source(client, source, csrf_token, url='https://news.test.invalid/changed')
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    saved = client.post(action, data=form)
    assert saved.status_code == 302
    if when == 'after':
        edit_source(client, source, csrf_token, url='https://news.test.invalid/changed')
    with app.app_context():
        page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
        assert page.select_one('[data-preview-status]').get_text(strip=True) == 'stale'
        assert 'Configuration changed' in page.get_text()


@pytest.mark.parametrize('change', ['toggle', 'url'])
def test_source_configuration_aba_does_not_restore_old_preview_form(client, source, csrf_token, fetch_network, change):
    version_url = save_candidate(client, source, csrf_token)
    action, form = preview_form(client, version_url)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    if change == 'toggle':
        for _ in range(2):
            assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    else:
        edit_source(client, source, csrf_token, url='https://news.test.invalid/changed')
        edit_source(client, source, csrf_token)
    assert client.post(action, data=form).status_code == 409
    assert not fetch_network.processes
