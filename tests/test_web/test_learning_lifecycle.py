"""Learning lifecycle via real Admin controls and externally delivered tasks."""
import time
import subprocess

import pytest

from bs4 import BeautifulSoup

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


def test_failed_learning_requires_source_cooldown_even_with_fresh_capture(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    bad = recipe_for(source)
    bad['feed']['url'] = 'https://news.test.invalid/not-retained'
    model.provider.reply = bad
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'exhausted'
    _, report = base.policy.captured_preview(client, source, csrf_token, fetch_network)
    again, data = base.form_at(client, report, 'form[data-learning-start]')
    assert client.post(again, data=data).status_code == 409
    assert client.post(action, data=fields).location == started.location
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert page.select_one('[data-learning-cooldown]').get_text(strip=True)
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 21601)
    again, data = base.form_at(client, report, 'form[data-learning-start]')
    newer = client.post(again, data=data)
    assert newer.status_code == 302 and newer.location != started.location
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, newer.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 3
    assert client.get('/api/v1/news').json['total'] == 0


def test_admin_can_retry_only_unadmitted_work_without_resetting_session_or_rounds(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    app.config['LLM_DAILY_BUDGET_USD'] = '0.01'
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'blocked' and not model.provider.calls
    before = BeautifulSoup(client.get(started.location).text, 'html.parser')
    retry, data = base.form_at(client, started.location, 'form[data-learning-retry]')
    data['note'] = '<script>Reviewed quota; no admitted call</script>'
    app.config['LLM_DAILY_BUDGET_USD'] = '1'
    assert client.post(retry, data=data).location == started.location
    duplicate = dict(data, note='must not overwrite the first decision')
    assert client.post(retry, data=duplicate).location == started.location
    queued = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert queued.select_one('[data-learning-rounds]').get_text(strip=True) == '1 / 3'
    assert queued.select_one('[data-learning-cooldown]').get_text() == before.select_one('[data-learning-cooldown]').get_text()
    assert len(queued.select('[data-learning-retry-event]')) == 1
    assert '<script>Reviewed quota; no admitted call</script>' in queued.get_text()
    assert not queued.select('[data-learning-retry-event] script')
    assert 'must not overwrite' not in queued.get_text()
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert base.state(client, started.location) == 'awaiting_validation'
    assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '2 / 3'
    assert page.select_one('[data-learning-spent]').get_text(strip=True) == '0.002000'
    assert len(model.provider.calls) == 1
    assert 'Reviewed quota' not in str(model.provider.calls)
    assert client.post(retry, data=duplicate).location == started.location
    base.deliver(learning_io)
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('change', ['deadline', 'cancel', 'revoke'])
def test_invalidated_work_does_not_launch_a_parser_after_the_model_returns(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, change):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    launches = []
    original = subprocess.Popen
    def after_call(kwargs):
        if change == 'deadline':
            now = time.time()
            monkeypatch.setattr(time, 'time', lambda: now + 181)
        elif change == 'cancel':
            cancel, data = base.form_at(client, started.location, 'form[data-learning-cancel]')
            assert client.post(cancel, data=data).status_code == 302
        else:
            revoke, data = base.policy.revoke_form(client, source)
            assert client.post(revoke, data=data).status_code == 302
        def observe(command, *args, **kwargs):
            if any(str(part).endswith('_parse_worker.py') for part in command):
                launches.append(command)
            return original(command, *args, **kwargs)
        monkeypatch.setattr(subprocess, 'Popen', observe)
    model.provider.before = after_call
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert not launches
    assert base.state(client, started.location) == ('cancelled' if change == 'cancel' else 'blocked')
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert page.select_one('[data-learning-spent]').get_text(strip=True) == '0.002000'
    assert not page.select('[data-learning-candidate]')


def test_lost_ack_of_rejected_round_cannot_block_a_newer_running_round(
        app, db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    bad = recipe_for(source)
    bad['feed']['url'] = 'https://news.test.invalid/not-retained'
    model.provider.reply = bad
    second_started, release = Event(), Event()
    def provider(kwargs):
        if len(model.provider.calls) == 2:
            second_started.set()
            assert release.wait(10)
    model.provider.before = provider
    armed, fired, futures = [], [], []
    def boundary(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE crawl_repair_attempt ') and 'rejected' in parameters:
            armed.append(True)
    def worker():
        with app.app_context():
            # New round requires its own committed message, not the old envelope.
            from app.crawlers.learning_tasks import recover
            recover.run()
            base.deliver(learning_io)
    with ThreadPoolExecutor(max_workers=1) as pool:
        def lost_ack(session):
            if armed and not fired:
                fired.append(True)
                model.provider.reply = recipe_for(source)
                futures.append(pool.submit(worker))
                assert second_started.wait(10)
                raise OperationalError(None, None, RuntimeError('synthetic finish acknowledgement loss'))
        event.listen(db.engine, 'before_cursor_execute', boundary)
        event.listen(Session, 'after_commit', lost_ack)
        try:
            base.deliver(learning_io)
        finally:
            release.set()
            for future in futures:
                future.result(timeout=15)
            event.remove(db.engine, 'before_cursor_execute', boundary)
            event.remove(Session, 'after_commit', lost_ack)
    assert fired
    assert base.state(client, started.location) == 'awaiting_validation'
    assert len(model.provider.calls) == 2


def blocked_request(app, client, source, csrf_token, fetch_network, learning_io):
    app.config['LLM_DAILY_BUDGET_USD'] = '0.01'
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    base.deliver(learning_io)
    retry, data = base.form_at(client, started.location, 'form[data-learning-retry]')
    data['note'] = 'Reviewed configuration, no provider call admitted'
    return started.location, retry, data


@pytest.mark.parametrize('change', ['deadline', 'cancelled', 'revoke', 'source_aba', 'history', 'evidence', 'disabled'])
def test_safe_retry_rechecks_authority_and_never_extends_deadline(
        db, app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, change):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    if change == 'deadline':
        now = time.time()
        monkeypatch.setattr(time, 'time', lambda: now + 181)
    elif change == 'cancelled':
        # A queued cancellation is irrevocable even if an old retry form survives.
        assert client.post(retry, data=data).status_code == 302
        action, fields = base.form_at(client, location, 'form[data-learning-cancel]')
        assert client.post(action, data=fields).status_code == 302
        data['after_round'] = '0'  # Not the already-acknowledged request.
    elif change == 'revoke':
        action, fields = base.policy.revoke_form(client, source)
        assert client.post(action, data=fields).status_code == 302
    elif change == 'source_aba':
        for _ in range(2):
            assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    elif change == 'history':
        with db.engine.begin() as conn:
            conn.exec_driver_sql('UPDATE crawl_learning_history SET history_complete=0')
    elif change == 'evidence':
        next(evidence_dir.glob('*.json')).unlink()
    else:
        app.config['CRAWL_LEARNING_ENABLED'] = False
    assert client.post(retry, data=data).status_code == 409
    assert not model.provider.calls
    assert base.state(client, location) == ('cancelled' if change == 'cancelled' else 'blocked')


@pytest.mark.parametrize('kind', ['unknown', 'settled', 'reconciled'])
def test_provider_admission_always_disqualifies_retry_even_if_money_is_known(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, kind):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    if kind == 'settled':
        model.provider.reply = {'not': 'a recipe'}
    else:
        model.provider.error = TimeoutError('synthetic lost response')
    base.deliver(learning_io)
    if kind == 'reconciled':
        from tests.test_llm.test_budget_admin import correction
        page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
        form = page.select_one('[data-reservation-state=unknown] form')
        assert client.post(form['action'], data=correction(form)).status_code == 302
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert not page.select('form[data-learning-retry]')
    response = client.post(started.location + '/retry', data={
        'csrf_token': csrf_token(), 'after_round': '1', 'note': 'Never permits another paid attempt'})
    assert response.status_code == 409
    assert base.state(client, started.location) == 'blocked'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('field,value', [('note', ''), ('note', 'x' * 301), ('after_round', '3'),
                                       ('after_round', '-1'), ('csrf_token', ''), ('cost_limit', '1')])
def test_retry_rejects_untrusted_controls(app, client, source, csrf_token, fetch_network, evidence_dir,
                                        learning_io, model, field, value):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    data[field] = value
    assert client.post(retry, data=data).status_code == 400
    assert base.state(client, location) == 'blocked' and not model.provider.calls


def test_retry_cannot_replenish_rounds_or_original_time_allowance(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    for expected in (2, 3):
        assert client.post(retry, data=data).status_code == 302
        base.deliver(learning_io)  # Still over budget; this round consumes no provider admission.
        page = BeautifulSoup(client.get(location).text, 'html.parser')
        assert page.select_one('[data-learning-rounds]').get_text(strip=True) == f'{expected} / 3'
        if expected == 2:
            retry, data = base.form_at(client, location, 'form[data-learning-retry]')
            data['note'] = 'Second explicit review'
    assert not page.select('form[data-learning-retry]')
    assert len(page.select('[data-learning-retry-event]')) == 2
    assert not model.provider.calls


def test_deadline_expiring_while_loading_retry_evidence_does_not_corrupt_history(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    import os
    import stat
    location, retry, data = blocked_request(app, client, source, csrf_token, fetch_network, learning_io)
    fstat, now = os.fstat, time.time()
    def delayed(fd):
        info = fstat(fd)
        if stat.S_ISREG(info.st_mode):
            monkeypatch.setattr(time, 'time', lambda: now + 181)
        return info
    with monkeypatch.context() as patch:
        patch.setattr(os, 'fstat', delayed)
        assert client.post(retry, data=data).status_code == 409
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
    assert not page.select('[data-learning-retry-event]')
    assert not model.provider.calls
