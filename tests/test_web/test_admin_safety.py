"""Admin actions must not lock the owner out, 500 on history, or silently stop crawling."""
from bs4 import BeautifulSoup

from app.models.crawl_schema import CrawlSchemaVersion, CrawlSourceProfile
from app.models.llm import LLMConfig, LLMUsageLog
from app.models.setting import SystemSetting
from app.models.source import NewsSource
from app.models.user import User


def _token(client, path):
    return BeautifulSoup(client.get(path).text, 'html.parser').select_one('input[name=csrf_token]')['value']


def _flash(response):
    return BeautifulSoup(response.text, 'html.parser').get_text(' ', strip=True)


def _source(db):
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://news.test.invalid/',
                        feed_type='rss', category='national')
    db.session.add(source)
    db.session.commit()
    return source


# ── users ──────────────────────────────────────────────────────────

def _edit_user(client, user, **changes):
    path = f'/admin/users/{user.id}/edit'
    data = {'csrf_token': _token(client, path), 'email': user.email, 'name': user.name,
            'preferred_language': 'zh', 'is_active_user': 'on', 'is_admin': 'on', **changes}
    return client.post(path, data={k: v for k, v in data.items() if v is not None}, follow_redirects=True)


def test_admin_cannot_deactivate_own_account(db, client, login, users):
    login('admin')

    _edit_user(client, users['admin'], is_active_user=None)

    assert db.session.get(User, users['admin'].id).is_active_user is True


def test_passwords_are_validated_on_the_server(db, client, login, users):
    login('admin')
    token = _token(client, '/admin/users/new')

    response = client.post('/admin/users/new', follow_redirects=True, data={
        'csrf_token': token, 'email': 'weak@test.invalid', 'name': 'weak', 'password': 'short'})

    assert User.query.filter_by(email='weak@test.invalid').first() is None
    assert 'at least 8 characters' in _flash(response)

    before = db.session.get(User, users['owner'].id).password_hash
    response = _edit_user(client, users['owner'], is_admin=None, password='short')
    assert db.session.get(User, users['owner'].id).password_hash == before
    assert 'at least 8 characters' in _flash(response)


def test_duplicate_email_on_edit_is_refused_not_a_server_error(db, client, login, users):
    login('admin')

    response = _edit_user(client, users['owner'], is_admin=None, email=users['other'].email)

    assert response.status_code == 200
    assert 'already' in _flash(response)
    assert db.session.get(User, users['owner'].id).email == 'owner@test.invalid'


def test_user_with_authored_crawl_records_is_not_deleted(db, client, login, users):
    source = _source(db)
    profile = CrawlSourceProfile(source_id=source.id)
    db.session.add(profile)
    db.session.flush()
    db.session.add(CrawlSchemaVersion(profile_id=profile.id, recipe={}, recipe_hash='a' * 64,
                                      base_generation=0, created_by_id=users['other'].id))
    db.session.commit()
    login('admin')

    response = client.post(f'/admin/users/{users["other"].id}/delete', follow_redirects=True,
                           data={'csrf_token': _token(client, '/admin/users')})

    assert response.status_code == 200
    assert db.session.get(User, users['other'].id) is not None
    assert 'Deactivate' in _flash(response)


# ── LLM config ─────────────────────────────────────────────────────

def test_llm_config_with_usage_history_is_not_deleted(db, client, login):
    config = LLMConfig(provider='openai', model='synthetic')
    db.session.add(config)
    db.session.flush()
    db.session.add(LLMUsageLog(config_id=config.id, task_type='translate'))
    db.session.commit()
    login('admin')

    response = client.post(f'/admin/llm-config/{config.id}/delete', follow_redirects=True,
                           data={'csrf_token': _token(client, '/admin/llm-config')})

    assert response.status_code == 200
    assert db.session.get(LLMConfig, config.id) is not None
    assert 'usage history' in _flash(response)


# ── daily crawl schedule ───────────────────────────────────────────

def test_settings_refuse_invalid_crawl_hour_and_timezone(db, client, login):
    SystemSetting.set('crawl_daily_hour', '1')
    SystemSetting.set('crawl_timezone', 'Europe/Paris')
    db.session.commit()
    login('admin')
    token = _token(client, '/admin/settings')

    response = client.post('/admin/settings', follow_redirects=True, data={
        'csrf_token': token, 'crawl_daily_hour': '25', 'crawl_timezone': 'Mars/Base'})

    assert 'Invalid' in _flash(response)
    assert SystemSetting.get('crawl_daily_hour') == '1'
    assert SystemSetting.get('crawl_timezone') == 'Europe/Paris'


# ── irreversible actions ask first ─────────────────────────────────

def test_irreversible_actions_ask_for_confirmation(db, client, login):
    source = _source(db)
    login('admin')

    settings = BeautifulSoup(client.get('/admin/settings').text, 'html.parser')
    for action in ['/admin/crawl-all-now', '/admin/email-send-digest']:
        form = settings.select_one(f'form[action="{action}"]')
        handlers = (form.get('onsubmit') or '') + (form.select_one('button').get('onclick') or '')
        assert 'confirm(' in handlers, action

    policy = BeautifulSoup(client.get(f'/admin/sources/{source.id}/crawl-config/policies').text, 'html.parser')
    assert 'confirm(' in policy.select_one('form[data-policy-revoke]')['onsubmit']
