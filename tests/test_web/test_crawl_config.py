"""Admin business HTTP is the M2 seam; no test-only endpoints or live I/O."""
import json

import pytest
from bs4 import BeautifulSoup
from werkzeug.datastructures import MultiDict
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def no_dispatch_or_model(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Saving a candidate must not dispatch tasks or call a model')

    monkeypatch.setattr('celery.app.base.Celery.send_task', blocked)
    monkeypatch.setattr('litellm.completion', blocked)


@pytest.fixture
def source(client, login, csrf_token):
    login('admin')
    response = client.post('/admin/sources/new', data={
        'name': 'Candidate source', 'slug': 'candidate-source',
        'url': 'https://news.test.invalid/', 'feed_type': 'rss',
        'feed_url': 'https://news.test.invalid/feed', 'category': 'national',
        'crawl_frequency_minutes': '60', 'is_active': 'on',
        'csrf_token': csrf_token(),
    })
    assert response.status_code == 302
    page = BeautifulSoup(client.get('/admin/sources').text, 'html.parser')
    source_id = int(page.select_one('a[href$="/edit"]')['href'].split('/')[-2])
    return source_id


def recipe_for(source_id):
    return {
        'format_version': 1, 'output_contract': 'article.v1', 'target_kind': 'news',
        'source_id': source_id, 'locale': 'en', 'transport': 'http', 'extractor': 'rss',
        'identity_policy': 'legacy-compatible-url-v1',
        'feed': {'url': 'https://news.test.invalid/feed',
                 'fields': {'title': 'title', 'url': 'link', 'external_id': 'id'}},
    }


def test_admin_saves_durable_candidate_without_activating_or_ingesting(app, client, source, csrf_token):
    path = f'/admin/sources/{source}/crawl-config'
    recipe = recipe_for(source)
    response = client.post(path, data={'recipe': json.dumps(recipe), 'csrf_token': csrf_token()})
    assert response.status_code == 302
    # The suite keeps an outer app context. Use a fresh framework context to
    # observe committed HTTP state, not an ORM identity map/uncommitted snapshot.
    with app.app_context():
        detail = client.get(response.location)
        assert detail.status_code == 200
        page = BeautifulSoup(detail.text, 'html.parser')
        assert page.select_one('[data-version-status]').get_text(strip=True) == 'Candidate'
        assert json.loads(page.select_one('pre[data-recipe]').get_text()) == recipe
        listing = client.get(path)
        assert listing.status_code == 200
        assert 'No active recipe' in listing.text
        assert BeautifulSoup(listing.text, 'html.parser').select_one(f'a[href="{response.location}"]')
        assert client.get('/api/v1/news').json['total'] == 0


def test_source_list_exposes_the_real_configuration_page(client, source):
    page = BeautifulSoup(client.get('/admin/sources').text, 'html.parser')
    link = page.select_one(f'a[href="/admin/sources/{source}/crawl-config"]')
    assert link is not None
    assert client.get(link['href']).status_code == 200


@pytest.mark.parametrize('actor', ['anonymous', 'owner'])
def test_candidate_pages_and_saving_require_admin(app, client, source, csrf_token, login, actor):
    path = f'/admin/sources/{source}/crawl-config'
    saved = client.post(path, data={'recipe': json.dumps(recipe_for(source)), 'csrf_token': csrf_token()})
    if actor == 'anonymous':
        probe = app.test_client()
        token = BeautifulSoup(probe.get('/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')['value']
    else:
        login('owner')
        probe, token = client, csrf_token()
    for response in [probe.get(path), probe.get(saved.location), probe.post(path, data={
            'recipe': json.dumps(recipe_for(source)), 'csrf_token': token})]:
        assert response.status_code == 302
        assert ('/auth/login' in response.location) if actor == 'anonymous' else response.location == '/'
    login('admin')
    assert len(BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')) == 1


def test_saving_keeps_csrf_protection(client, source):
    path = f'/admin/sources/{source}/crawl-config'
    assert client.post(path, data={'recipe': json.dumps(recipe_for(source))}).status_code == 400
    assert not BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')


@pytest.mark.parametrize('field', ['status', 'active_schema_id', 'created_by_id', 'base_generation', 'version_id', 'allowed_hosts'])
def test_candidate_form_rejects_server_owned_metadata(client, source, csrf_token, field):
    path = f'/admin/sources/{source}/crawl-config'
    response = client.post(path, data={
        'recipe': json.dumps(recipe_for(source)), 'csrf_token': csrf_token(), field: 'forged',
    })
    assert response.status_code == 400
    assert not BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')


@pytest.mark.parametrize('case', ['json', 'duplicate_key', 'deep', 'large', 'source', 'code', 'policy', 'active'])
def test_invalid_recipe_never_creates_a_candidate(client, source, csrf_token, case):
    path = f'/admin/sources/{source}/crawl-config'
    recipe = recipe_for(source)
    if case == 'source':
        recipe['source_id'] = source + 1
    elif case == 'code':
        recipe['script'] = 'DO-NOT-ECHO-UNTRUSTED'
    elif case == 'policy':
        recipe['allowed_hosts'] = ['127.0.0.1']
    elif case == 'active':
        recipe['active'] = True
    document = json.dumps(recipe)
    if case == 'json':
        document = '{DO-NOT-ECHO-UNTRUSTED'
    elif case == 'duplicate_key':
        document = document[:-1] + ', "source_id": 999}'
    elif case == 'deep':
        document = '[' * 2000 + '0' + ']' * 2000
    elif case == 'large':
        document = ' ' * 65537
    response = client.post(path, data={'recipe': document, 'csrf_token': csrf_token()})
    assert response.status_code == 400
    assert 'DO-NOT-ECHO-UNTRUSTED' not in response.text
    assert not BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')


def test_saving_changed_recipe_preserves_the_old_version(app, client, source, csrf_token):
    path = f'/admin/sources/{source}/crawl-config'
    original = recipe_for(source)
    first = client.post(path, data={'recipe': json.dumps(original), 'csrf_token': csrf_token()})
    revised = {**original, 'locale': 'fr'}
    second = client.post(path, data={'recipe': json.dumps(revised), 'csrf_token': csrf_token()})
    assert first.location != second.location
    assert client.post(first.location, data={'recipe': json.dumps(revised), 'csrf_token': csrf_token()}).status_code == 405
    with app.app_context():
        for url, expected in [(first.location, original), (second.location, revised)]:
            page = BeautifulSoup(client.get(url).text, 'html.parser')
            assert json.loads(page.select_one('pre[data-recipe]').get_text()) == expected
        assert len(BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')) == 2


def test_candidate_cannot_be_read_under_a_different_source(client, source, csrf_token):
    saved = client.post(f'/admin/sources/{source}/crawl-config', data={
        'recipe': json.dumps(recipe_for(source)), 'csrf_token': csrf_token(),
    })
    other = client.post('/admin/sources/new', data={
        'name': 'Other source', 'slug': 'other-source', 'url': 'https://other.test.invalid/',
        'feed_type': 'rss', 'category': 'national', 'csrf_token': csrf_token(),
    })
    assert other.status_code == 302
    rows = BeautifulSoup(client.get('/admin/sources').text, 'html.parser').select('tbody tr')
    row = next(row for row in rows if 'Other source' in row.get_text())
    other_id = row.select_one('a[href$="/edit"]')['href'].split('/')[-2]
    assert client.get(saved.location.replace(f'/sources/{source}/', f'/sources/{other_id}/')).status_code == 404
    assert client.get(saved.location).status_code == 200


def test_recipe_is_escaped_and_does_not_leak_to_public_sources(client, source, csrf_token):
    recipe = recipe_for(source)
    recipe['feed']['url'] += '?note=</pre><script>alert(1)</script>'
    saved = client.post(f'/admin/sources/{source}/crawl-config', data={
        'recipe': json.dumps(recipe), 'csrf_token': csrf_token(),
    })
    assert saved.status_code == 302
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert json.loads(page.select_one('pre[data-recipe]').get_text()) == recipe
    assert not any(script.get_text() == 'alert(1)' for script in page.select('script'))
    assert 'alert(1)' not in client.get('/api/v1/sources').text


def test_failed_save_is_private_and_a_fresh_request_can_retry(app, db, client, source, csrf_token, caplog):
    path = f'/admin/sources/{source}/crawl-config'
    with db.engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TRIGGER reject_candidate BEFORE INSERT ON crawl_schema_version
            BEGIN SELECT RAISE(FAIL, 'SENSITIVE-SQL-DETAIL'); END""")
    response = client.post(path, data={'recipe': json.dumps(recipe_for(source)), 'csrf_token': csrf_token()})
    assert response.status_code == 503
    assert 'SENSITIVE-SQL-DETAIL' not in response.text + caplog.text
    with app.app_context():
        page = client.get(path)
        assert page.status_code == 200
        assert not BeautifulSoup(page.text, 'html.parser').select('a[href*="/versions/"]')
    with db.engine.begin() as connection:
        connection.exec_driver_sql('DROP TRIGGER reject_candidate')
    retry = client.post(path, data={'recipe': json.dumps(recipe_for(source)), 'csrf_token': csrf_token()})
    assert retry.status_code == 302
    with app.app_context():
        assert client.get(retry.location).status_code == 200
        assert len(BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')) == 1


def test_success_response_needs_no_read_after_commit(db, client, source, csrf_token):
    committed = []

    def mark_commit(session):
        committed.append(True)

    def disconnect_after_commit(conn, cursor, statement, parameters, context, executemany):
        if committed and statement.lstrip().upper().startswith('SELECT'):
            raise OperationalError('synthetic read failure', {}, Exception('disconnected'))

    token = csrf_token()
    event.listen(Session, 'after_commit', mark_commit)
    event.listen(db.engine, 'before_cursor_execute', disconnect_after_commit)
    try:
        response = client.post(f'/admin/sources/{source}/crawl-config', data={
            'recipe': json.dumps(recipe_for(source)), 'csrf_token': token,
        })
        assert response.status_code == 302
    finally:
        event.remove(Session, 'after_commit', mark_commit)
        event.remove(db.engine, 'before_cursor_execute', disconnect_after_commit)
    assert client.get(response.location).status_code == 200


def test_sensitive_candidate_pages_are_not_cached_or_sent_as_referrers(client, source, csrf_token):
    path = f'/admin/sources/{source}/crawl-config'
    saved = client.post(path, data={'recipe': json.dumps(recipe_for(source)), 'csrf_token': csrf_token()})
    for response in [saved, client.get(path), client.get(saved.location)]:
        assert response.headers.get('Cache-Control') == 'no-store'
        assert response.headers.get('Referrer-Policy') == 'no-referrer'


def test_candidate_form_rejects_ambiguous_duplicate_recipe(client, source, csrf_token):
    path = f'/admin/sources/{source}/crawl-config'
    response = client.post(path, data=MultiDict([
        ('recipe', json.dumps(recipe_for(source))), ('recipe', '{"active":true}'),
        ('csrf_token', csrf_token()),
    ]))
    assert response.status_code == 400
    assert not BeautifulSoup(client.get(path).text, 'html.parser').select('a[href*="/versions/"]')
