"""Admin learning recovery/security at HTTP and external broker/provider boundaries."""
import time
import pytest
from bs4 import BeautifulSoup
from werkzeug.datastructures import MultiDict

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


@pytest.mark.parametrize('field', ['cost_limit', 'max_rounds', 'status', 'source_id', 'evidence', 'created_by_id', 'csrf_token'])
def test_start_rejects_injected_or_duplicate_controls(client, source, csrf_token, fetch_network, evidence_dir, learning_io, field):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    values = MultiDict(fields)
    values.add(field, 'untrusted')
    assert client.post(action, data=values).status_code == 400
    assert not learning_io


@pytest.mark.parametrize('actor', ['owner', 'anonymous'])
def test_learning_requires_admin_for_start_status_and_cancel(client, source, csrf_token, fetch_network, evidence_dir, learning_io, login, actor):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    cancel, data = base.form_at(client, started.location, 'form[data-learning-cancel]')
    if actor == 'owner':
        assert client.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password',
                                               'csrf_token': csrf_token()}).status_code == 302
    else:
        assert client.get('/auth/logout').status_code == 302
    assert client.get(started.location).status_code in (302, 403)
    assert client.post(action, data={'csrf_token': csrf_token()}).status_code in (302, 403)
    assert client.post(cancel, data={'csrf_token': csrf_token()}).status_code in (302, 403)


def test_broker_failure_preserves_intent_and_recovery_delivers_it(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, caplog):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    def unavailable(*args, **kwargs):
        raise OSError('PRIVATE_BROKER_SECRET')
    with monkeypatch.context() as patch:
        patch.setattr('celery.app.base.Celery.send_task', unavailable)
        started = client.post(action, data=fields)
    assert started.status_code == 302
    assert base.state(client, started.location) == 'queued'
    assert 'PRIVATE_BROKER_SECRET' not in caplog.text
    from app.crawlers.learning_tasks import recover
    recover.run()
    assert not learning_io
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 32)
    recover.run()
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


def test_worker_crash_retains_hold_and_recovery_never_repeats_uncertain_call(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    def crash(kwargs):
        raise SystemExit('synthetic worker exit')
    model.provider.before = crash
    with pytest.raises(SystemExit):
        base.deliver(learning_io)
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 181)
    from app.crawlers.learning_tasks import recover
    recover.run()
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'blocked'
    assert page.select_one('[data-learning-held]').get_text(strip=True) == '0.092160'
    assert len(model.provider.calls) == 1


def test_learning_stops_on_repeated_bad_recipe_without_network_or_articles(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    bad = recipe_for(source)
    bad['feed']['url'] = 'https://news.test.invalid/unseen'
    model.provider.reply = bad
    requests = len(fetch_network.events())
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'exhausted'
    assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '2 / 3'
    assert not page.select('a[data-learning-candidate]')
    assert len(model.provider.calls) == 2
    assert len(fetch_network.events()) == requests
    assert client.get('/api/v1/news').json['total'] == 0


@pytest.mark.parametrize('table,expected_calls,held', [('llm_reservation', 0, '0.000000'), ('llm_usage_log', 1, '0.092160')])
def test_accounting_failure_never_repeats_paid_work_and_preserves_holds(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, caplog,
        table, expected_calls, held):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    with db.engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE TRIGGER reject_learning BEFORE INSERT ON {table} BEGIN SELECT RAISE(FAIL, 'PRIVATE_ACCOUNTING_ERROR'); END")
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'blocked'
    assert page.select_one('[data-learning-held]').get_text(strip=True) == held
    assert not page.select('a[data-learning-candidate]')
    assert len(model.provider.calls) == expected_calls
    assert 'PRIVATE_ACCOUNTING_ERROR' not in caplog.text + str(page)


def test_parallel_duplicate_start_keeps_same_session_and_one_execution(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    cookie = client.get_cookie('session').value
    barrier = Barrier(2)
    def post():
        with app.app_context():
            browser = app.test_client()
            browser.set_cookie('session', cookie)
            barrier.wait(timeout=5)
            result = browser.post(action, data=fields)
            return result.status_code, result.location
    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = list(pool.map(lambda _: post(), range(2)))
    assert left == right and left[0] == 302
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    base.deliver(learning_io)
    assert base.state(client, left[1]) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


def test_no_csrf_or_cross_source_learning_access(client, source, csrf_token, fetch_network, evidence_dir, learning_io):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    assert client.post(action, data={}).status_code == 400
    assert client.post(action.replace(f'/sources/{source}/', '/sources/999/'), data=fields).status_code == 404
    started = client.post(action, data=fields)
    assert client.get(started.location.replace(f'/sources/{source}/', '/sources/999/')).status_code == 404
    cancel, data = base.form_at(client, started.location, 'form[data-learning-cancel]')
    assert client.post(cancel, data={}).status_code == 400
    assert client.post(cancel.replace(f'/sources/{source}/', '/sources/999/'), data=data).status_code == 404
    assert base.state(client, started.location) == 'queued'
