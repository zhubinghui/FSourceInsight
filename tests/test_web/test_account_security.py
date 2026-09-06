import pytest
from bs4 import BeautifulSoup

from app.models.user import KeywordSubscription


def test_anonymous_cannot_change_admin_password(client, users, csrf_token, login):
    response = client.post('/subscribe/settings', data={
        'email': users['admin'].email, 'password': 'attacker-password',
        'csrf_token': csrf_token(),
    })
    assert response.status_code == 302
    assert '/auth/login' in response.location
    login('admin')
    assert client.get('/admin/').status_code == 200


@pytest.mark.parametrize('path', ['/subscribe/', '/subscribe/manage', '/subscribe/settings'])
def test_subscription_pages_require_login(client, path):
    response = client.get(path)
    assert response.status_code == 302
    assert '/auth/login' in response.location


@pytest.mark.parametrize('actor', ['owner', 'admin'])
@pytest.mark.parametrize('path', ['/subscribe/', '/subscribe/manage', '/subscribe/settings'])
def test_email_cannot_select_another_account(client, users, login, actor, path):
    login(actor)
    assert client.get(path, query_string={'email': users['other'].email}).status_code == 403


def test_signed_in_user_cannot_reset_other_password(client, users, csrf_token, login):
    login()
    response = client.post('/subscribe/settings', data={
        'email': users['admin'].email, 'password': 'replacement-password',
        'csrf_token': csrf_token(),
    })
    assert response.status_code == 403
    login('admin')
    assert client.get('/admin/').status_code == 200


@pytest.mark.parametrize('operation', ['delete', 'toggle'])
def test_subscription_mutations_check_ownership(client, db, users, csrf_token, login, operation):
    sub = KeywordSubscription(user_id=users['other'].id, keyword='private-topic')
    db.session.add(sub)
    db.session.commit()
    sub_id = sub.id
    login()
    assert client.post(f'/subscribe/{sub_id}/{operation}', data={'csrf_token': csrf_token()}).status_code == 404
    login('other')
    page = client.get('/subscribe/manage')
    assert 'private-topic' in page.text
    assert BeautifulSoup(page.text, 'html.parser').select_one('tbody .badge').get_text(strip=True) == 'Active'


def test_owner_can_add_pause_resume_delete(client, users, csrf_token, login):
    login()
    response = client.post('/subscribe/', data={
        'keywords': 'semiconductor, semiconductor', 'csrf_token': csrf_token(),
    })
    assert response.status_code == 302
    page = client.get('/subscribe/manage')
    soup = BeautifulSoup(page.text, 'html.parser')
    action = soup.select_one('form[action$="/toggle"]')['action']
    assert client.post(action, data={'csrf_token': csrf_token()}).status_code == 302
    assert BeautifulSoup(client.get('/subscribe/manage').text, 'html.parser').select_one('tbody .badge').get_text(strip=True) == 'Paused'
    client.post(action, data={'csrf_token': csrf_token()})
    assert BeautifulSoup(client.get('/subscribe/manage').text, 'html.parser').select_one('tbody .badge').get_text(strip=True) == 'Active'
    client.post(action.replace('/toggle', '/delete'), data={'csrf_token': csrf_token()})
    assert 'semiconductor' not in client.get('/subscribe/manage').text


@pytest.mark.parametrize('old_password', ['', 'wrong-password'])
def test_password_change_requires_current_password(client, csrf_token, login, old_password):
    login()
    response = client.post('/subscribe/settings', data={
        'password': 'replacement-password', 'current_password': old_password,
        'csrf_token': csrf_token(),
    })
    assert response.status_code == 400
    login()
    assert client.get('/subscribe/settings').status_code == 200


def test_owner_can_change_password_without_email_selector(client, csrf_token, login):
    login()
    response = client.post('/subscribe/settings', data={
        'password': 'replacement-password', 'current_password': 'original-password',
        'preferred_language': 'en', 'csrf_token': csrf_token(),
    })
    assert response.status_code == 302
    login(password='replacement-password')
    assert client.get('/subscribe/settings').status_code == 200


@pytest.mark.parametrize('target', ['https://evil.invalid/', '//evil.invalid/', '/\\evil.invalid/', '\\evil.invalid', 'javascript:alert(1)'])
def test_login_rejects_unsafe_redirects(login, target):
    response = login(next_url=target)
    assert response.status_code == 302
    assert response.location == '/'


def test_login_keeps_local_next(login):
    assert login(next_url='/subscribe/settings').location == '/subscribe/settings'


def test_password_change_revokes_existing_sessions(app, client, csrf_token, login):
    login()
    second = app.test_client()
    token = BeautifulSoup(second.get('/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')['value']
    second.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password', 'csrf_token': token})
    assert second.get('/subscribe/settings').status_code == 200
    client.post('/subscribe/settings', data={
        'password': 'replacement-password', 'current_password': 'original-password',
        'csrf_token': csrf_token(),
    })
    response = second.get('/subscribe/settings')
    assert response.status_code == 302
    assert '/auth/login' in response.location


def test_disabled_user_cannot_login_or_keep_session(client, db, users, login):
    login()
    users['owner'].is_active_user = False
    db.session.commit()
    assert '/auth/login' in client.get('/subscribe/manage').location
    assert login().status_code == 200


@pytest.mark.parametrize('form', [
    {'password': 'short', 'current_password': 'original-password'},
    {'preferred_language': 'bad'},
])
def test_invalid_settings_rejected_without_changes(client, csrf_token, login, form):
    login()
    response = client.post('/subscribe/settings', data={**form, 'name': 'unexpected-name', 'csrf_token': csrf_token()})
    assert response.status_code == 400
    assert 'unexpected-name' not in client.get('/subscribe/settings').text


def test_anonymous_subscription_post_is_rejected(client, csrf_token):
    response = client.post('/subscribe/', data={'email': 'new@test.invalid', 'keywords': 'AI', 'csrf_token': csrf_token()})
    assert response.status_code == 302
    assert '/auth/login' in response.location


def test_settings_keep_csrf_protection(client, login):
    login()
    assert client.post('/subscribe/settings', data={'name': 'no token'}).status_code == 400
