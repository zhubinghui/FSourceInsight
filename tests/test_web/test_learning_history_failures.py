"""Workflow coverage failure windows; real HTTP/tasks, synthetic transports."""
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from tests.test_web import test_learning_history as history
from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


@pytest.mark.parametrize('table', ['crawl_repair_attempt', 'crawl_learning_history'])
def test_exposure_and_counter_fail_atomically_before_the_provider(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, caplog, table):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    with db.engine.begin() as conn:
        if table == 'crawl_repair_attempt':
            target = 'BEFORE INSERT ON crawl_repair_attempt'
        else:
            target = 'BEFORE UPDATE ON crawl_learning_history WHEN NEW.exposure_generation > OLD.exposure_generation'
        conn.exec_driver_sql(f"CREATE TRIGGER reject_history {target} BEGIN SELECT RAISE(FAIL, 'PRIVATE_HISTORY_ERROR'); END")
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'blocked'
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
    assert page.select_one('[data-history-exposures]').get_text(strip=True) == '0'
    assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '0 / 3'
    assert not model.provider.calls
    assert 'PRIVATE_HISTORY_ERROR' not in caplog.text + str(page)


def test_claim_commit_ack_loss_preserves_conservative_exposure_without_retrying_payment(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, caplog):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    fired = []
    def lost_ack(session):
        if not fired:
            fired.append(True)
            raise OperationalError(None, None, RuntimeError('PRIVATE_COMMIT_ACK'))
    event.listen(Session, 'after_commit', lost_ack)
    try:
        base.deliver(learning_io)
    finally:
        event.remove(Session, 'after_commit', lost_ack)
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert fired
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
    assert page.select_one('[data-history-exposures]').get_text(strip=True) == '1'
    assert base.state(client, started.location) == 'blocked'
    assert not model.provider.calls
    assert 'PRIVATE_COMMIT_ACK' not in caplog.text + str(page)


@pytest.mark.parametrize('when', ['before_payment', 'after_payment'])
def test_history_revocation_is_rechecked_at_paid_and_candidate_checkpoints(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, when):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    changed = []
    def damage():
        if not changed:
            changed.append(True)
            with db.engine.begin() as conn:
                conn.execute(text('UPDATE crawl_learning_history SET history_complete=0'))
    if when == 'before_payment':
        original = model.cache.get
        def read(key):
            damage()
            return original(key)
        monkeypatch.setattr(model.cache, 'get', read)
    else:
        model.provider.before = lambda kwargs: damage()
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert changed
    assert base.state(client, started.location) == 'blocked'
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'incomplete'
    assert not page.select('a[data-learning-candidate]')
    assert len(model.provider.calls) == (0 if when == 'before_payment' else 1)
    assert page.select_one('[data-learning-spent]').get_text(strip=True) == ('0.000000' if when == 'before_payment' else '0.002000')


@pytest.mark.parametrize('limit', ['0', '4097', 'not-a-number', True])
def test_invalid_history_scan_limits_never_allow_learning(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, limit):
    app.config['CRAWL_LEARNING_HISTORY_SCAN_LIMIT'] = limit
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    assert client.post(action, data=fields).status_code == 409
    assert not model.provider.calls
    assert not learning_io


def test_legacy_usage_alone_prevents_empty_history_bootstrap(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    from app.models import LLMUsageLog
    db.session.add(LLMUsageLog(config_id=model.config.id, task_type='crawl_schema', cost_usd='0.123456'))
    db.session.commit()
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    assert client.post(action, data=fields).status_code == 409
    assert not model.provider.calls
    assert not learning_io


def test_history_does_not_disappear_after_raw_evidence_is_removed(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location = history.learned(client, source, csrf_token, fetch_network, learning_io, model)
    for path in evidence_dir.glob('*.json'):
        path.unlink()
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
    assert page.select_one('[data-history-exposures]').get_text(strip=True) == '1'
    assert page.select_one('[data-exposure-document]')
    assert 'Not independently validated' in page.get_text()


def test_wrong_control_row_cannot_be_mistaken_for_an_empty_workflow(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    with db.engine.begin() as conn:
        conn.execute(text('INSERT INTO crawl_learning_history (id,session_generation,exposure_generation,history_complete) VALUES (2,5,5,1)'))
    assert client.post(action, data=fields).status_code == 409
    assert not model.provider.calls
    assert not learning_io
