"""Paid-attempt fault injection only at SQL/provider/clock system boundaries."""
from types import SimpleNamespace

from bs4 import BeautifulSoup
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.llm.client import LLMClient


@pytest.mark.parametrize('total', [True, -1, 151, '150'])
def test_inconsistent_total_usage_is_unknown_not_released_or_cached(app, llm_env, monkeypatch, total):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    replies = []
    def provider(**kwargs):
        replies.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=total),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='result'))])
    monkeypatch.setattr('litellm.completion', provider)
    with pytest.raises(RuntimeError, match='usage unknown'):
        LLMClient().translate('uncertain charge')
    with pytest.raises(RuntimeError, match='budget exceeded'):
        LLMClient().translate('uncertain charge')
    assert len(replies) == 1


@pytest.mark.parametrize('stage', ['admission', 'settlement'])
def test_database_failure_never_creates_an_unreserved_retry(app, db, llm_env, stage):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    table = 'llm_reservation' if stage == 'admission' else 'llm_usage_log'
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith(f'INSERT INTO {table} '):
            raise RuntimeError('synthetic accounting outage')
    event.listen(db.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic accounting outage'):
            LLMClient().translate('first input')
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail)
    assert len(llm_env.provider.calls) == (0 if stage == 'admission' else 1)
    if stage == 'settlement':
        with pytest.raises(RuntimeError, match='budget exceeded'):
            LLMClient().translate('another input')
        assert len(llm_env.provider.calls) == 1
    else:
        assert LLMClient().translate('another input') == 'Translated text'


@pytest.mark.parametrize('lost_commit', [1, 2])
def test_commit_ack_loss_retains_committed_accounting_without_paid_fallback(app, llm_env, lost_commit):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    commits = []
    def lost_ack(session):
        commits.append(1)
        if len(commits) == lost_commit:
            raise RuntimeError('synthetic acknowledgement lost after commit')
    event.listen(Session, 'after_commit', lost_ack)
    try:
        with pytest.raises(RuntimeError, match='acknowledgement lost'):
            LLMClient().translate('lost ack')
    finally:
        event.remove(Session, 'after_commit', lost_ack)
    assert len(llm_env.provider.calls) == lost_commit - 1
    if lost_commit == 1:
        with pytest.raises(RuntimeError, match='budget exceeded'):
            LLMClient().translate('new input')
    else:
        assert LLMClient().translate('new input') == 'Translated text'


def test_supplier_ceiling_overrun_is_audited_and_blocks_further_billing(db, llm_env, client, login, monkeypatch):
    calls = []
    def overrun(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=2000, completion_tokens=50),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='result'))])
    monkeypatch.setattr('litellm.completion', overrun)
    with pytest.raises(RuntimeError, match='ceiling overrun'):
        LLMClient().translate('violated contract')
    with pytest.raises(RuntimeError, match='ceiling overrun'):
        LLMClient().translate('new input')
    assert len(calls) == 1
    login('admin')
    row = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser').select_one('[data-reservation-state=overrun]')
    assert row is not None and '0.021000' in row.get_text()


def test_large_supplier_overrun_remains_auditable_without_overflowing_legacy_usage_column(app, db, llm_env, client, login, monkeypatch):
    # Emulate the real legacy MySQL NUMERIC(10,6) limit in the offline DB.
    llm_env.config.cost_per_1k_input = '100'
    db.session.commit()
    with db.engine.begin() as conn:
        conn.execute(text("CREATE TRIGGER legacy_cost_precision BEFORE INSERT ON llm_usage_log WHEN NEW.cost_usd > 9999.999999 BEGIN SELECT RAISE(ABORT, 'legacy cost precision'); END"))
    app.config['LLM_DAILY_BUDGET_USD'] = 0
    def provider(**kwargs):
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100_000_000, completion_tokens=0),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='result'))])
    monkeypatch.setattr('litellm.completion', provider)
    with pytest.raises(RuntimeError, match='ceiling overrun'):
        LLMClient().translate('extreme overrun')
    login('admin')
    row = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser').select_one('[data-reservation-state=overrun]')
    assert row is not None and '10000000.000000' in row.get_text()


def test_reconciliation_does_not_reauthorize_disproved_token_ceilings(app, db, llm_env, client, login, csrf_token, monkeypatch):
    app.config['LLM_DAILY_BUDGET_USD'] = 1
    config_path = f'/admin/llm-config/{llm_env.config.id}/edit'
    calls = []
    def provider(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=2000, completion_tokens=50),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='result'))])
    monkeypatch.setattr('litellm.completion', provider)
    with pytest.raises(RuntimeError, match='ceiling overrun'):
        LLMClient().translate('overrun')
    login('admin')
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    form = page.select_one('[data-reservation-state=overrun] form')
    assert client.post(form['action'], data={
        'csrf_token': form.select_one('[name=csrf_token]')['value'], 'expected_state': 'overrun',
        'final_cost': '0.021', 'evidence_note': 'Final invoice', 'confirmed_final': '1', 'confirmed_stopped': '1',
    }).status_code == 302
    with pytest.raises(RuntimeError):
        LLMClient().translate('must not pay under disproved terms')
    assert len(calls) == 1
    # Only an explicitly reviewed, compatible new ceiling admits another call.
    assert client.post(config_path, data={
        'csrf_token': csrf_token(config_path), 'provider': 'synthetic', 'model': 'primary',
        'tasks': ['translate'], 'max_tokens': '4096', 'cost_per_1k_input': '0.01', 'cost_per_1k_output': '0.02',
        'billing_input_limit': '2048', 'billing_output_limit': '4096', 'billing_reviewed': '1',
    }).status_code == 302
    assert LLMClient().translate('new reviewed terms') == 'result'
    assert len(calls) == 2


def test_decimal_rounding_never_turns_a_fractional_microdollar_charge_into_free_usage(db, llm_env, client, login):
    llm_env.config.cost_per_1k_input = llm_env.config.cost_per_1k_output = '0.000001'
    db.session.commit()
    LLMClient().translate('fractional price')
    login('admin')
    row = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser').select_one('[data-reservation-state=settled]')
    assert '0.000006 / 0.000001' in row.get_text()
