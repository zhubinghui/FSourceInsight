"""Private evidence behavior through admin HTTP, real filesystem and M1 engine."""
import pytest
import subprocess
import os
import json
import time
import hashlib
import fcntl
from sqlalchemy import text
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_preview as preview_fixtures

source = preview_fixtures.source
fetch_network = preview_fixtures.fetch_network
no_dispatch_or_model = preview_fixtures.no_dispatch_or_model
save_candidate = preview_fixtures.save_candidate
preview_form = preview_fixtures.preview_form


@pytest.fixture
def evidence_dir(app, tmp_path):
    path = tmp_path / 'private-evidence'
    path.mkdir(mode=0o700)
    app.config['CRAWL_EVIDENCE_DIR'] = str(path)
    return path


def capture(client, source_id, csrf_token, fetch_network):
    version = save_candidate(client, source_id, csrf_token)
    page = BeautifulSoup(client.get(version).text, 'html.parser')
    checkbox = page.select_one('input[name="retain_evidence"]')
    assert checkbox is not None and not checkbox.has_attr('checked')
    action, form = preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news', retain_evidence='1')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview_fixtures.FEED, 'headers': {'Content-Type': 'application/rss+xml'},
    }})
    result = client.post(action, data=form)
    return version, result


def test_admin_explicitly_retains_private_evidence(app, client, source, csrf_token, fetch_network, evidence_dir):
    version, result = capture(client, source, csrf_token, fetch_network)
    assert result.status_code == 302
    with app.app_context():
        response = client.get(result.location)
        page = BeautifulSoup(response.text, 'html.parser')
        assert page.select_one('[data-evidence-status]').get_text(strip=True) == 'available'
        assert '24 hours' in page.get_text()
        assert str(evidence_dir) not in response.text
        assert '<rss' not in response.text
        assert client.get('/api/v1/news').json['total'] == 0
        assert BeautifulSoup(client.get(version).text, 'html.parser').select_one('[data-version-status]').get_text(strip=True) == 'Candidate'
    files = list(evidence_dir.glob('*.json'))
    assert len(files) == 1
    assert files[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('problem', ['unset', 'missing', 'symlink', 'symlink_loop', 'permissions', 'checkout'])
def test_unsafe_storage_is_rejected_before_fetch(app, client, source, csrf_token, fetch_network, evidence_dir, problem):
    if problem == 'unset':
        app.config['CRAWL_EVIDENCE_DIR'] = None
    elif problem == 'missing':
        app.config['CRAWL_EVIDENCE_DIR'] = str(evidence_dir / 'missing')
    elif problem in {'symlink', 'symlink_loop'}:
        link = evidence_dir.parent / 'symlink-store'
        link.symlink_to(link if problem == 'symlink_loop' else evidence_dir, target_is_directory=True)
        app.config['CRAWL_EVIDENCE_DIR'] = str(link)
    elif problem == 'permissions':
        evidence_dir.chmod(0o755)
    else:
        app.config['CRAWL_EVIDENCE_DIR'] = os.getcwd()
    _, saved = capture(client, source, csrf_token, fetch_network)
    assert saved.status_code == 503
    assert not fetch_network.processes
    assert not list(evidence_dir.glob('*.json'))


def test_default_preview_does_not_retain_even_with_storage(client, source, csrf_token, fetch_network, evidence_dir):
    version = save_candidate(client, source, csrf_token)
    action, data = preview_form(client, version)
    data.update(allowed_hosts='other.test.invalid', quality_kind='news')
    saved = client.post(action, data=data)
    assert saved.status_code == 302
    assert BeautifulSoup(client.get(saved.location).text, 'html.parser').select_one('[data-evidence-status]').get_text(strip=True) == 'not_retained'
    assert not list(evidence_dir.iterdir())


@pytest.mark.parametrize('expired_orphan', [False, True])
def test_byte_capacity_refuses_without_evicting_live_files(client, source, csrf_token, fetch_network, evidence_dir, expired_orphan):
    for i in range(22):
        path = evidence_dir / f'{i:032x}.json'
        with path.open('wb') as stream:
            stream.truncate(3 * 1024 * 1024)
        path.chmod(0o600)
    if expired_orphan:
        path = evidence_dir / ('e' * 32 + '.json')
        path.write_bytes(b'expired orphan')
        path.chmod(0o600)
        past = time.time() - 86401
        os.utime(path, (past, past))
    _, saved = capture(client, source, csrf_token, fetch_network)
    assert saved.status_code == 503
    assert len(list(evidence_dir.glob('*.json'))) == 22


def test_busy_store_fails_without_waiting_or_writing(client, source, csrf_token, fetch_network, evidence_dir):
    fd = os.open(evidence_dir / '.evidence.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _, saved = capture(client, source, csrf_token, fetch_network)
        assert saved.status_code == 503
        assert not list(evidence_dir.glob('*.json'))
    finally:
        os.close(fd)


@pytest.mark.parametrize('fault', ['fsync', 'sql'])
def test_failed_save_has_no_report_and_orphan_is_cleanable(db, client, source, csrf_token, fetch_network, evidence_dir, monkeypatch, caplog, fault):
    with monkeypatch.context() as patch:
        if fault == 'fsync':
            def fail(fd):
                raise OSError('PRIVATE_FAILURE_DETAIL')
            patch.setattr(os, 'fsync', fail)
        else:
            with db.engine.begin() as conn:
                conn.exec_driver_sql("CREATE TRIGGER reject_evidence BEFORE INSERT ON crawl_preview_report BEGIN SELECT RAISE(FAIL, 'PRIVATE_FAILURE_DETAIL'); END")
        version, saved = capture(client, source, csrf_token, fetch_network)
    assert saved.status_code == 503
    assert 'PRIVATE_FAILURE_DETAIL' not in saved.text + caplog.text
    assert not BeautifulSoup(client.get(version).text, 'html.parser').select('a[href*="/previews/"]')
    assert client.get('/api/v1/news').json['total'] == 0
    assert len(list(evidence_dir.glob('*.json'))) == 1
    future = time.time() + 86401
    monkeypatch.setattr(time, 'time', lambda: future)
    page = BeautifulSoup(client.get(version.rsplit('/versions/', 1)[0]).text, 'html.parser')
    result = client.post(page.select_one('form[data-cleanup]')['action'], data={'csrf_token': csrf_token()})
    assert result.status_code == 302
    assert not list(evidence_dir.glob('*.json'))


def test_full_store_refuses_retention_without_overwriting(client, source, csrf_token, fetch_network, evidence_dir):
    for i in range(32):
        path = evidence_dir / f'{i:032x}.json'
        path.write_bytes(b'existing private evidence')
        path.chmod(0o600)
    _, saved = capture(client, source, csrf_token, fetch_network)
    assert saved.status_code == 503
    assert len(list(evidence_dir.glob('*.json'))) == 32
    assert all(path.read_bytes() == b'existing private evidence' for path in evidence_dir.glob('*.json'))


@pytest.mark.parametrize('change', ['permissions', 'hardlink', 'missing', 'modified', 'symlink', 'fifo', 'oversized'])
def test_insecure_evidence_files_are_unavailable(client, source, csrf_token, fetch_network, evidence_dir, change):
    _, saved = capture(client, source, csrf_token, fetch_network)
    action, form = replay_form(client, saved.location)
    path = next(evidence_dir.glob('*.json'))
    if change == 'permissions':
        path.chmod(0o644)
    elif change == 'hardlink':
        os.link(path, evidence_dir.parent / 'external-hardlink')
    elif change == 'missing':
        path.unlink()
    elif change == 'modified':
        path.write_bytes(b'PRIVATE_RAW_BODY_NOT_VALID')
    elif change == 'oversized':
        with path.open('r+b') as stream:
            stream.truncate(3 * 1024 * 1024 + 1)
    else:
        path.unlink()
        if change == 'symlink':
            path.symlink_to(evidence_dir.parent / 'outside-file')
        else:
            os.mkfifo(path, 0o600)
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert page.select_one('[data-evidence-status]').get_text(strip=True) == 'unavailable'
    assert client.post(action, data=form).status_code == 409


def mutate_report(db, location, mutation):
    report_id = int(location.rsplit('/', 1)[1])
    with db.engine.begin() as conn:
        value = json.loads(conn.execute(text('SELECT report FROM crawl_preview_report WHERE id=:id'), {'id': report_id}).scalar_one())
        mutation(value)
        conn.execute(text('UPDATE crawl_preview_report SET report=:data WHERE id=:id'), {'data': json.dumps(value), 'id': report_id})


@pytest.mark.parametrize('problem', ['body_hash', 'unsafe_url', 'extra_field', 'duplicate_key'])
def test_bundle_checksum_alone_is_not_valid_evidence(db, client, source, csrf_token, fetch_network, evidence_dir, problem):
    _, saved = capture(client, source, csrf_token, fetch_network)
    action, form = replay_form(client, saved.location)
    path = next(evidence_dir.glob('*.json'))
    doc = json.loads(path.read_bytes())
    if problem == 'body_hash':
        doc['pages'][0]['observation']['snapshot_id'] = 'sha256:' + '0' * 64
    elif problem == 'unsafe_url':
        doc['pages'][0]['document_url'] = 'http://127.0.0.1/private'
    elif problem == 'extra_field':
        doc['allowed_hosts'] = ['127.0.0.1']
    raw = json.dumps(doc).encode()
    if problem == 'duplicate_key':
        raw = raw.replace(b'"format": 1', b'"format": 0, "format": 1')
    path.write_bytes(raw)
    mutate_report(db, saved.location, lambda data: data['evidence'].update(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw)))
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert page.select_one('[data-evidence-status]').get_text(strip=True) == 'unavailable'
    assert client.post(action, data=form).status_code == 409


def test_no_snapshots_cannot_claim_retained_evidence(client, source, csrf_token, fetch_network, evidence_dir):
    version = save_candidate(client, source, csrf_token)
    action, data = preview_form(client, version)
    data.update(allowed_hosts='other.test.invalid', quality_kind='news', retain_evidence='1')
    result = client.post(action, data=data)
    assert result.status_code == 503
    assert not list(evidence_dir.glob('*.json'))
    assert not fetch_network.processes


def test_reference_paths_cannot_escape_private_store(db, client, source, csrf_token, fetch_network, evidence_dir, monkeypatch):
    _, saved = capture(client, source, csrf_token, fetch_network)
    action, form = replay_form(client, saved.location)
    mutate_report(db, saved.location, lambda doc: doc['evidence'].update(key='../outside-file'))
    original = os.open

    def guarded(path, *args, **kwargs):
        assert path != '../outside-file', 'Attempted path escape'
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, 'open', guarded)
    assert client.post(action, data=form).status_code == 409
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert page.select_one('[data-evidence-status]').get_text(strip=True) == 'unavailable'


def test_copied_reference_cannot_replace_another_capture(db, client, source, csrf_token, fetch_network, evidence_dir):
    version, saved = capture(client, source, csrf_token, fetch_network)
    action, form = replay_form(client, saved.location)
    post, data = preview_form(client, version)
    data.update(allowed_hosts='news.test.invalid', quality_kind='news', retain_evidence='1')
    other = client.post(post, data=data)
    assert other.status_code == 302
    reference = []
    mutate_report(db, other.location, lambda doc: reference.append(doc['evidence']))
    mutate_report(db, saved.location, lambda doc: doc.update(evidence=reference[0]))
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert page.select_one('[data-evidence-status]').get_text(strip=True) == 'unavailable'
    assert client.post(action, data=form).status_code == 409
    assert BeautifulSoup(client.get(other.location).text, 'html.parser').select_one('[data-evidence-status]').get_text(strip=True) == 'available'


def test_admin_cleans_only_expired_evidence(client, source, csrf_token, fetch_network, evidence_dir, monkeypatch):
    version, saved = capture(client, source, csrf_token, fetch_network)
    replay_action, _ = replay_form(client, saved.location)
    page = BeautifulSoup(client.get(version.rsplit('/versions/', 1)[0]).text, 'html.parser')
    cleanup = page.select_one('form[data-cleanup]')
    assert cleanup is not None
    future = time.time() + 86401
    monkeypatch.setattr(time, 'time', lambda: future)
    fresh = evidence_dir / ('f' * 32 + '.json')
    fresh.write_bytes(b'fresh orphan')
    fresh.chmod(0o600)
    os.utime(fresh, (future, future))
    page = BeautifulSoup(client.get(saved.location).text, 'html.parser')
    assert page.select_one('[data-evidence-status]').get_text(strip=True) == 'expired'
    assert client.post(replay_action, data={'csrf_token': csrf_token()}).status_code == 409
    result = client.post(cleanup['action'], data={'csrf_token': csrf_token()})
    assert result.status_code == 302
    assert 'Removed 1 expired evidence bundle' in client.get(result.location).text
    assert list(evidence_dir.glob('*.json')) == [fresh]


@pytest.mark.parametrize('when', ['before', 'during', 'expires_during'])
def test_replay_rechecks_inputs_and_expiry(app, client, source, csrf_token, fetch_network, evidence_dir, monkeypatch, when):
    _, saved = capture(client, source, csrf_token, fetch_network)
    action, data = replay_form(client, saved.location)
    if when == 'before':
        preview_fixtures.edit_source(client, source, csrf_token, url='https://news.test.invalid/changed')
    original = subprocess.Popen
    changed = []

    def spawn(command, **kwargs):
        assert not str(command[-1]).endswith('_fetch_worker.py')
        if not changed and when != 'before':
            changed.append(True)
            if when == 'expires_during':
                future = time.time() + 86401
                monkeypatch.setattr(time, 'time', lambda: future)
            else:
                with app.app_context():
                    preview_fixtures.edit_source(client, source, csrf_token, url='https://news.test.invalid/changed')
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    assert client.post(action, data=data).status_code == 409


def test_partial_capture_never_fetches_missing_pages_on_replay(client, source, csrf_token, fetch_network, evidence_dir, monkeypatch):
    recipe = preview_fixtures.recipe_for(source)
    recipe.pop('feed')
    recipe['extractor'] = 'html'
    recipe['list_pages'] = [{'url': 'https://news.test.invalid/' + path, 'item_selector': 'article', 'fields': {
        'title': {'selector': 'a', 'read': 'text'}, 'url': {'selector': 'a', 'read': 'attr', 'attr': 'href'},
    }} for path in ['one', 'missing']]
    version = save_candidate(client, source, csrf_token, recipe)
    action, data = preview_form(client, version)
    data.update(allowed_hosts='news.test.invalid', quality_kind='news', retain_evidence='1')
    fetch_network.configure(routes={'https://news.test.invalid/one': {'body': '<article><a href="/story">Research news</a></article>'},
                                    'https://news.test.invalid/missing': {'status': 503}})
    saved = client.post(action, data=data)
    assert saved.status_code == 302
    action, data = replay_form(client, saved.location)
    original = subprocess.Popen

    def spawn(command, **kwargs):
        assert not str(command[-1]).endswith('_fetch_worker.py')
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    response = client.post(action, data=data)
    assert response.status_code == 200
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-preview-status]').get_text(strip=True) == 'partial'
    assert 'no_evidence' in response.text
    assert client.get('/api/v1/news').json['total'] == 0


@pytest.mark.parametrize('actor', ['anonymous', 'owner', 'no_csrf'])
@pytest.mark.parametrize('operation', ['capture', 'replay', 'cleanup'])
def test_evidence_actions_require_admin_and_csrf(app, client, source, csrf_token, fetch_network, evidence_dir, actor, operation):
    version, saved = capture(client, source, csrf_token, fetch_network)
    if operation == 'capture':
        action, data = preview_form(client, version)
        data.update(allowed_hosts='news.test.invalid', quality_kind='news', retain_evidence='1')
    elif operation == 'replay':
        action, data = replay_form(client, saved.location)
    else:
        page = BeautifulSoup(client.get(version.rsplit('/versions/', 1)[0]).text, 'html.parser')
        action, data = page.select_one('form[data-cleanup]')['action'], {'csrf_token': csrf_token()}
    probe = client
    if actor == 'anonymous':
        probe = app.test_client()
        data['csrf_token'] = BeautifulSoup(probe.get('/auth/login').text, 'html.parser').select_one('input[name="csrf_token"]')['value']
    elif actor == 'owner':
        assert client.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password', 'csrf_token': csrf_token()}).status_code == 302
        data['csrf_token'] = csrf_token()
    else:
        data.pop('csrf_token')
    result = probe.post(action, data=data)
    assert result.status_code == (400 if actor == 'no_csrf' else 302)
    if actor != 'no_csrf':
        assert probe.get(saved.location).status_code == 302
        assert ('/auth/login' in result.location) if actor == 'anonymous' else result.location == '/'
    assert len(list(evidence_dir.glob('*.json'))) == 1


@pytest.mark.parametrize('field', ['recipe', 'allowed_hosts', 'capture_id', 'evidence', 'status'])
def test_replay_rejects_forged_controls(client, source, csrf_token, fetch_network, evidence_dir, field):
    _, saved = capture(client, source, csrf_token, fetch_network)
    action, data = replay_form(client, saved.location)
    data[field] = 'FORGED'
    assert client.post(action, data=data).status_code == 400


def test_replay_cannot_cross_candidate_binding(client, source, csrf_token, fetch_network, evidence_dir):
    version, saved = capture(client, source, csrf_token, fetch_network)
    action, data = replay_form(client, saved.location)
    second = save_candidate(client, source, csrf_token)
    assert client.post(action.replace(version, second), data=data).status_code == 404
    response = client.post(action, data=data)
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Referrer-Policy'] == 'no-referrer'


def replay_form(client, location):
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    form = page.select_one('form[data-replay]')
    assert form is not None
    return form['action'], {node['name']: node['value'] for node in form.select('input[name]')}


def test_retained_report_replays_without_network_or_business_writes(app, db, client, source, csrf_token, fetch_network, evidence_dir, monkeypatch):
    version, saved = capture(client, source, csrf_token, fetch_network)
    action, form = replay_form(client, saved.location)
    mutate_report(db, saved.location, lambda doc: doc['samples'][0].update(title='CACHED PROJECTION IS NOT THE SNAPSHOT'))
    original = subprocess.Popen

    def spawn(command, **kwargs):
        assert not str(command[-1]).endswith('_fetch_worker.py'), 'Replay tried to fetch'
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    with app.app_context():
        response = client.post(action, data=form)
        assert response.status_code == 200
        page = BeautifulSoup(response.text, 'html.parser')
        assert 'Offline snapshot replay' in page.get_text()
        assert page.select_one('[data-field="title"]').get_text(strip=True) == 'Grenoble research'
        assert page.select_one('[data-preview-status]').get_text(strip=True) == 'ready'
        assert client.get('/api/v1/news').json['total'] == 0
        assert len(BeautifulSoup(client.get(version).text, 'html.parser').select('a[href*="/previews/"]')) == 1
