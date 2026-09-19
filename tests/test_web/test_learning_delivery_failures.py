"""Storage/clock failures at the real HTTP/task/SDK boundary, no helper mocks."""
import os
import stat
import time

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for
from tests.test_web.test_learning_lifecycle import blocked_request

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


@pytest.mark.parametrize('checkpoint,rounds', [('claim_evidence', 0), ('admission_evidence', 1), ('admission_last_query', 1)])
def test_slow_authority_reads_cannot_admit_after_the_original_deadline(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, checkpoint, rounds):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    model.provider.reply = recipe_for(source)
    clock, fired, reads = time.time(), [], []
    original = os.fstat
    def fstat(fd):
        value = original(fd)
        if stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode) == 0o600:
            reads.append(fd)
            if checkpoint.endswith('_evidence') and len(reads) == (1 if checkpoint == 'claim_evidence' else 2):
                fired.append(True)
                monkeypatch.setattr(time, 'time', lambda: clock + 181)
        return value
    def slow_query(conn, cursor, statement, parameters, context, many):
        if (checkpoint == 'admission_last_query' and not fired and statement.startswith('SELECT')
                and 'llm_reservation.learning_attempt_id =' in statement and 'llm_reservation.config_id =' in statement):
            fired.append(True)
            monkeypatch.setattr(time, 'time', lambda: clock + 181)
    monkeypatch.setattr(os, 'fstat', fstat)
    event.listen(db.engine, 'after_cursor_execute', slow_query)
    try:
        base.deliver(learning_io)
    finally:
        event.remove(db.engine, 'after_cursor_execute', slow_query)
    assert fired, 'Must cross the real read boundary before checking a deadline'
    assert not model.provider.calls
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'blocked'
    assert page.select_one('[data-learning-rounds]').text == f'{rounds} / 3'
    assert not page.select('[data-learning-reservation]')
    assert not page.select('[data-learning-candidate]')


@pytest.mark.parametrize('operation', ['consume', 'recover'])
def test_unavailable_storage_does_not_escape_private_errors_or_discard_intent(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, caplog, operation):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    def broken(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO llm_budget_gate '):
            raise OperationalError(None, None, RuntimeError('PRIVATE_DB_DELIVERY'))
    event.listen(db.engine, 'before_cursor_execute', broken)
    try:
        if operation == 'consume':
            base.deliver(learning_io)
        else:
            from app.crawlers.learning_tasks import recover
            recover.run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', broken)
    assert base.state(client, started.location) == 'queued'
    assert not model.provider.calls and len(learning_io) == 1
    assert 'PRIVATE_DB_DELIVERY' not in caplog.text


def test_unclaimed_old_worker_error_cannot_close_a_new_retry(
        db, app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location, retry, fields = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    old_message = list(learning_io[-1][1])
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    assert client.post(retry, data=fields).location == location
    fired = []
    def broken(conn, cursor, statement, parameters, context, many):
        if not fired and statement.startswith('INSERT INTO llm_budget_gate '):
            fired.append(True)
            raise OperationalError(None, None, RuntimeError('synthetic old claim unavailable'))
    event.listen(db.engine, 'before_cursor_execute', broken)
    try:
        from app.crawlers.learning_tasks import learn
        learn.run(*old_message)
    finally:
        event.remove(db.engine, 'before_cursor_execute', broken)
    assert fired and base.state(client, location) == 'queued'
    assert not model.provider.calls
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


def test_zero_round_retry_changes_delivery_without_inventing_an_attempt(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    old_message = list(learning_io[-1][1])
    fired = []
    def broken(conn, cursor, statement, parameters, context, many):
        if not fired and statement.startswith('INSERT INTO llm_budget_gate '):
            fired.append(True)
            raise OperationalError(None, None, RuntimeError('synthetic first claim unavailable'))
    event.listen(db.engine, 'before_cursor_execute', broken)
    try:
        base.deliver(learning_io)
    finally:
        event.remove(db.engine, 'before_cursor_execute', broken)
    assert fired and base.state(client, started.location) == 'blocked'
    retry, fields = base.form_at(client, started.location, 'form[data-learning-retry]')
    assert fields['after_round'] == '0'
    assert client.post(retry, data={**fields, 'note': 'Storage restored before any provider admission'}).status_code == 302
    from app.crawlers.learning_tasks import learn
    learn.run(*old_message)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'queued'
    assert page.select_one('[data-history-exposures]').text == '0'
    assert not model.provider.calls
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1


def test_dispatch_commit_ack_loss_preserves_spacing_and_current_intent(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, caplog):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    armed, fired = [], []
    def boundary(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE crawl_repair_session ') and 'dispatch_due_at=' in statement:
            armed.append(True)
    def lost_ack(session):
        if armed and not fired:
            fired.append(True)
            raise OperationalError(None, None, RuntimeError('PRIVATE_DISPATCH_ACK'))
    event.listen(db.engine, 'before_cursor_execute', boundary)
    event.listen(Session, 'after_commit', lost_ack)
    try:
        started = client.post(action, data=fields)
    finally:
        event.remove(db.engine, 'before_cursor_execute', boundary)
        event.remove(Session, 'after_commit', lost_ack)
    assert fired and started.status_code == 302 and not learning_io
    from app.crawlers.learning_tasks import recover
    recover.run()
    assert not learning_io
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 32)
    recover.run()
    assert len(learning_io) == 1
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 1
    assert 'PRIVATE_DISPATCH_ACK' not in caplog.text


def test_rejected_round_ack_loss_recovers_only_with_a_new_message(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    old_message = list(learning_io[-1][1])
    bad = recipe_for(source)
    bad['feed']['url'] = 'https://news.test.invalid/not-retained'
    model.provider.reply = bad
    armed, fired = [], []
    def boundary(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE crawl_repair_attempt ') and 'rejected' in parameters:
            armed.append(True)
    def lost_ack(session):
        if armed and not fired:
            fired.append(True)
            raise OperationalError(None, None, RuntimeError('synthetic rejected acknowledgement loss'))
    event.listen(db.engine, 'before_cursor_execute', boundary)
    event.listen(Session, 'after_commit', lost_ack)
    try:
        base.deliver(learning_io)
    finally:
        event.remove(db.engine, 'before_cursor_execute', boundary)
        event.remove(Session, 'after_commit', lost_ack)
    assert fired and base.state(client, started.location) == 'queued'
    model.provider.reply = recipe_for(source)
    from app.crawlers.learning_tasks import learn, recover
    learn.run(*old_message)
    assert base.state(client, started.location) == 'queued' and len(model.provider.calls) == 1
    recover.run()
    assert learning_io[-1][1] != old_message
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'awaiting_validation'
    assert page.select_one('[data-learning-rounds]').text == '2 / 3'
    assert page.select_one('[data-learning-spent]').text == '0.004000'
    assert len(model.provider.calls) == 2


@pytest.mark.parametrize('when', ['before_claim', 'before_admission'])
def test_missing_dispatch_state_never_acquires_or_pays(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, when):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    fired = []
    def erase(conn, cursor, statement, parameters, context, many):
        if not fired and statement.startswith('INSERT INTO crawl_repair_attempt '):
            fired.append(True)
            conn.exec_driver_sql('UPDATE crawl_repair_session SET dispatch_due_at=NULL')
    if when == 'before_claim':
        with db.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE crawl_repair_session SET dispatch_due_at=NULL')
    else:
        event.listen(db.engine, 'after_cursor_execute', erase)
    try:
        base.deliver(learning_io)
    finally:
        if when == 'before_admission':
            event.remove(db.engine, 'after_cursor_execute', erase)
            assert fired
    from app.crawlers.learning_tasks import recover
    recover.run()
    assert base.state(client, started.location) == 'blocked'
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert not model.provider.calls and not page.select('[data-learning-reservation]')
    assert not page.select('form[data-learning-retry]')
    assert len(learning_io) == 1


def test_due_running_work_is_not_a_new_paid_lease(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    def crash(kwargs):
        raise SystemExit('synthetic lost worker, not a real process kill')
    model.provider.before = crash
    with pytest.raises(SystemExit):
        base.deliver(learning_io)
    clock = time.time()
    monkeypatch.setattr(time, 'time', lambda: clock + 32)
    from app.crawlers.learning_tasks import recover
    recover.run()
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'running'
    assert page.select_one('[data-learning-held]').text == '0.092160'
    assert len(learning_io) == len(model.provider.calls) == 1
    monkeypatch.setattr(time, 'time', lambda: clock + 181)
    recover.run()
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'blocked'
    assert page.select_one('[data-learning-held]').text == '0.092160'
    assert not page.select('form[data-learning-retry]')


def test_legacy_terminal_candidate_remains_readable_without_reenabling_execution(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    with db.engine.begin() as conn:
        conn.exec_driver_sql('UPDATE crawl_repair_session SET dispatch_due_at=NULL')
    from app.crawlers.learning_tasks import recover
    recover.run()
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert page.select_one('[data-learning-delivery]').text == 'unavailable'
    assert page.select_one('[data-learning-history]').text == 'tracked'
    assert page.select_one('[data-validation-status]').text == 'awaiting_evidence'
    assert client.get(page.select_one('[data-learning-candidate]')['href']).status_code == 200
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(learning_io) == len(model.provider.calls) == 1
