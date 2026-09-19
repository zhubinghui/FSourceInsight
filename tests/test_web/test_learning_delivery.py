"""Versioned delivery through Admin HTTP, real tasks and external boundaries."""
import time

import pytest
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for
from tests.test_web.test_learning_lifecycle import blocked_request

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


def test_message_from_before_admin_retry_cannot_execute_the_new_decision(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location, retry, fields = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    old_message = list(learning_io[-1][1])
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    model.provider.reply = recipe_for(source)
    assert client.post(retry, data=fields).location == location
    from app.crawlers.learning_tasks import learn
    learn.run(*old_message)
    assert base.state(client, location) == 'queued'
    assert not model.provider.calls
    assert BeautifulSoup(client.get(location).text, 'html.parser').select_one('[data-learning-rounds]').text == '1 / 3'
    base.deliver(learning_io)
    assert base.state(client, location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('broker_failure', [False, True])
def test_dispatch_has_a_shared_thirty_second_minimum_even_after_broker_failure(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, monkeypatch, caplog, broker_failure):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    initial = int(time.time()) + .75
    clock = [initial]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    attempted = []
    def send(self, name, args=None, **kw):
        assert kw == {'queue': 'crawl_learn'}
        attempted.append((name, args))
        if broker_failure and len(attempted) == 1:
            raise OSError('PRIVATE_DELIVERY_BROKER')
        learning_io.append((name, args))
    monkeypatch.setattr('celery.app.base.Celery.send_task', send)
    started = client.post(action, data=fields)
    from app.crawlers.learning_tasks import recover
    assert client.post(action, data=fields).location == started.location
    recover.run()
    assert len(attempted) == 1
    clock[0] = initial + 29.99
    recover.run()
    assert len(attempted) == 1
    clock[0] = initial + 31
    recover.run()
    recover.run()
    assert len(attempted) == 2 and attempted[0] == attempted[1]
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert page.select_one('[data-learning-rounds]').text == '0 / 3'
    assert 'PRIVATE_DELIVERY_BROKER' not in caplog.text


@pytest.mark.parametrize('invalid', [None, '', 0, [], 'ld1:' + '0' * 64])
def test_legacy_or_wrong_message_cannot_claim_a_current_intent(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, invalid):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    from app.crawlers.learning_tasks import learn
    identity = learning_io[-1][1][0]
    if invalid is None:
        learn.run(identity)  # Deliberate old producer protocol.
    else:
        learn.run(identity, invalid)
    assert base.state(client, started.location) == 'queued'
    assert not model.provider.calls
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('field', ['delivery_key', 'dispatch_due_at', 'retry_count'])
def test_http_cannot_inject_delivery_authority(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, field):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    assert client.post(action, data={**fields, field: 'untrusted'}).status_code == 400
    assert not learning_io


def test_parallel_recovery_shares_one_publication_interval(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.crawlers.learning_tasks import recover
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    now, barrier = time.time(), Barrier(2)
    monkeypatch.setattr(time, 'time', lambda: now + 32)
    def sweep():
        with app.app_context():
            barrier.wait(timeout=5)
            recover.run()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: sweep(), range(2)))
    assert len(learning_io) == 2 and learning_io[0] == learning_io[1]
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('action_kind', ['expired', 'cancelled', 'disabled'])
def test_ineligible_intents_are_not_redispatched(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, monkeypatch, action_kind):
    from app.crawlers.learning_tasks import recover
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    if action_kind == 'cancelled':
        cancel, data = base.form_at(client, started.location, 'form[data-learning-cancel]')
        assert client.post(cancel, data=data).status_code == 302
    if action_kind == 'disabled':
        app.config['CRAWL_LEARNING_ENABLED'] = False
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + (181 if action_kind == 'expired' else 32))
    recover.run()
    assert len(learning_io) == 1
    assert base.state(client, started.location) == {'expired': 'blocked', 'cancelled': 'cancelled', 'disabled': 'queued'}[action_kind]


def test_admin_shows_eligibility_not_a_broker_ack_or_a_new_deadline(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert page.select_one('[data-learning-delivery]').text == 'learning-delivery.v1'
    assert page.select_one('[data-learning-dispatch-key]').text == learning_io[-1][1][1]
    assert page.select_one('[data-learning-dispatch-at]').text.endswith('UTC')
    assert 'not a broker receipt' in page.text
    assert not page.select('input[name=delivery_key],input[name=dispatch_due_at]')
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    finished = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert not finished.select('[data-learning-dispatch-key]')
    assert base.state(client, started.location) == 'awaiting_validation'
