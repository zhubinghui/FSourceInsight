"""Retry audit is atomic, private and fenced at real HTTP/storage boundaries."""
import time

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from werkzeug.datastructures import MultiDict

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_learning_lifecycle import blocked_request
from tests.test_web.test_crawl_config import recipe_for

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


@pytest.mark.parametrize('target', ['record', 'counter'])
def test_retry_write_failure_preserves_blocked_session_and_complete_history(
        db, app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, caplog, target):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    trigger = ('BEFORE INSERT ON crawl_repair_retry' if target == 'record' else
               'BEFORE UPDATE ON crawl_repair_session WHEN NEW.retry_count > OLD.retry_count')
    with db.engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE TRIGGER fail_retry {trigger} BEGIN SELECT RAISE(FAIL, 'PRIVATE_RETRY_SQL'); END")
    response = client.post(retry, data=data)
    assert response.status_code == 503
    assert base.state(client, location) == 'blocked'
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
    assert not page.select('[data-learning-retry-event]')
    assert not model.provider.calls
    assert 'PRIVATE_RETRY_SQL' not in caplog.text + response.text


def test_retry_commit_ack_loss_does_not_duplicate_audit_or_paid_work(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    fired = []
    def lost_ack(session):
        if not fired:
            fired.append(True)
            raise OperationalError(None, None, RuntimeError('synthetic retry commit acknowledgement lost'))
    event.listen(Session, 'after_commit', lost_ack)
    try:
        assert client.post(retry, data=data).status_code == 503
    finally:
        event.remove(Session, 'after_commit', lost_ack)
    assert base.state(client, location) == 'queued'
    assert client.post(retry, data=data).status_code == 302
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert len(page.select('[data-learning-retry-event]')) == 1
    assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '2 / 3'
    assert base.state(client, location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('damage', ['delete', 'note', 'counter', 'cooldown'])
def test_lost_or_modified_retry_audit_blocks_paid_admission(
        db, app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, damage):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    if damage != 'cooldown':
        assert client.post(retry, data=data).status_code == 302
    statement = {'delete': 'DELETE FROM crawl_repair_retry',
                 'note': "UPDATE crawl_repair_retry SET note='forged approval'",
                 'counter': 'UPDATE crawl_repair_session SET retry_count=0',
                 'cooldown': 'UPDATE crawl_repair_session SET cooldown_until=NULL'}[damage]
    with db.engine.begin() as conn:
        conn.exec_driver_sql(statement)
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    if damage == 'cooldown':
        assert client.post(retry, data=data).status_code == 409
    else:
        base.deliver(learning_io)
    assert not model.provider.calls
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert base.state(client, location) == 'blocked'
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'unavailable'
    assert not page.select('[data-learning-retry-event]')
    assert 'forged approval' not in page.get_text()


@pytest.mark.parametrize('actor', ['owner', 'anonymous'])
def test_retry_requires_admin_and_does_not_expose_history(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, actor):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    if actor == 'anonymous':
        client.get('/auth/logout')
    else:
        assert client.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password',
                                                'csrf_token': csrf_token()}).status_code == 302
    assert client.get(location).status_code == 302
    response = client.post(retry, data=dict(data, csrf_token=csrf_token()))
    assert response.status_code == 302 and response.location != location
    assert not model.provider.calls


def test_retry_rejects_duplicate_fields_and_cross_source_identity(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    values = MultiDict(data)
    values.add('after_round', '0')
    assert client.post(retry, data=values).status_code == 400
    other = retry.replace(f'/sources/{source}/', '/sources/999/')
    assert client.post(other, data=data).status_code == 404
    assert base.state(client, location) == 'blocked'


def test_parallel_retry_requests_keep_one_decision_and_one_new_round(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    cookie, barrier = client.get_cookie('session').value, Barrier(2)
    def post():
        with app.app_context():
            browser = app.test_client()
            browser.set_cookie('session', cookie)
            barrier.wait(timeout=5)
            result = browser.post(retry, data=data)
            return result.status_code, result.location
    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = list(pool.map(lambda _: post(), range(2)))
    assert left == right == (302, location)
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert len(page.select('[data-learning-retry-event]')) == 1
    assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '2 / 3'
    assert len(model.provider.calls) == 1


def test_retry_broker_loss_is_recoverable_without_resetting_limits(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, caplog):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    def unavailable(*args, **kwargs):
        raise OSError('PRIVATE_RETRY_BROKER')
    with monkeypatch.context() as patch:
        patch.setattr('celery.app.base.Celery.send_task', unavailable)
        assert client.post(retry, data=data).status_code == 302
    from app.crawlers.learning_tasks import recover
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 32)
    recover.run()
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, location) == 'awaiting_validation'
    assert 'PRIVATE_RETRY_BROKER' not in caplog.text
    assert len(model.provider.calls) == 1


def test_failed_duplicate_claim_cannot_cancel_a_running_owner(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    def duplicate(kwargs):
        fired = []
        def unavailable(conn, cursor, statement, parameters, context, many):
            if not fired and statement.startswith('INSERT INTO llm_budget_gate '):
                fired.append(True)
                raise OperationalError(None, None, RuntimeError('synthetic failed duplicate claim'))
        event.listen(db.engine, 'before_cursor_execute', unavailable)
        try:
            base.deliver(learning_io)
        finally:
            event.remove(db.engine, 'before_cursor_execute', unavailable)
        assert fired
    model.provider.before = duplicate
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1
