"""Admission/accounting through public client calls and the external provider."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from bs4 import BeautifulSoup

from app.models.llm import LLMConfig, LLMUsageLog

import pytest

from app.llm.client import LLMClient


def test_inflight_call_reserves_last_balance_across_independent_clients(app, llm_env):
    # Configured ceiling costs $0.092160; either request fits, both do not.
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    entered, release = Event(), Event()

    def hold(call):
        if call['messages'][-1]['content'] == 'first input':
            entered.set()
            assert release.wait(10), 'test provider not released'
    llm_env.provider.before = hold

    def first():
        with app.app_context():
            return LLMClient().translate('first input')

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(first)
        try:
            assert entered.wait(5)
            # Independent request must fail before entering the paid transport.
            with pytest.raises(RuntimeError, match='budget exceeded'):
                LLMClient().translate('second input')
            assert len(llm_env.provider.calls) == 1
        finally:
            release.set()
        assert pending.result(timeout=5) == 'Translated text'
    # Actual cost is $0.002; after settlement a fresh call fits again.
    llm_env.provider.before = None
    assert LLMClient().translate('third input') == 'Translated text'


@pytest.mark.parametrize('field,value', [
    ('billing_input_limit', None), ('billing_output_limit', None),
    ('billing_input_limit', 0), ('billing_output_limit', -1),
    ('billing_output_limit', 100), ('cost_per_1k_input', None),
    ('cost_per_1k_output', '-0.01'),
])
def test_unreviewed_or_invalid_billing_terms_never_reach_provider(db, llm_env, field, value):
    setattr(llm_env.config, field, value)
    db.session.commit()
    with pytest.raises(RuntimeError):
        LLMClient().translate('unapproved terms')
    assert llm_env.provider.calls == []


def test_unknown_usage_holds_balance_and_does_not_cache_result(app, llm_env, monkeypatch):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    calls = []
    def unavailable_usage(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(
            finish_reason='stop', message=SimpleNamespace(content='Paid text'))])
    monkeypatch.setattr('litellm.completion', unavailable_usage)
    with pytest.raises(RuntimeError, match='usage unknown'):
        LLMClient().translate('same input')
    with pytest.raises(RuntimeError, match='budget exceeded'):
        LLMClient().translate('same input')
    assert len(calls) == 1


def test_failed_attempt_holds_unknown_cost_across_day_boundary(app, llm_env, monkeypatch):
    import time
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    llm_env.provider.error = TimeoutError('supplier response lost')
    with pytest.raises(TimeoutError):
        LLMClient().translate('first input')
    # A new client/process/day must not release a crashed/unknown permit.
    next_day = time.time() + 86400
    monkeypatch.setattr(time, 'time', lambda: next_day)
    llm_env.provider.error = None
    with pytest.raises(RuntimeError, match='budget exceeded'):
        LLMClient().translate('new input')
    assert len(llm_env.provider.calls) == 1


def test_paid_invalid_response_leaves_insufficient_balance_for_fallback(app, db, llm_env):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.093
    db.session.add(LLMConfig(provider='second', model='backup', tasks=['ner'],
                             cost_per_1k_input='0.01', cost_per_1k_output='0.02',
                             billing_input_limit=1024, billing_output_limit=4096))
    db.session.commit()
    llm_env.provider.reply = 'invalid JSON'
    with pytest.raises(RuntimeError, match='budget exceeded'):
        LLMClient().extract_companies('a report')
    assert len(llm_env.provider.calls) == 1
    assert LLMUsageLog.query.one().success is False


def test_admin_can_review_billing_caps_and_enable_paid_requests(client, login, csrf_token, db, llm_env):
    llm_env.config.billing_input_limit = llm_env.config.billing_output_limit = None
    db.session.commit()
    login('admin')
    path = f'/admin/llm-config/{llm_env.config.id}/edit'
    page = BeautifulSoup(client.get(path).text, 'html.parser')
    assert page.select_one('input[name=billing_input_limit]') is not None
    saved = client.post(path, data={
        'csrf_token': csrf_token(path), 'provider': 'synthetic', 'model': 'primary',
        'tasks': ['translate'], 'max_tokens': '4096',
        'cost_per_1k_input': '0.01', 'cost_per_1k_output': '0.02',
        'billing_input_limit': '1024', 'billing_output_limit': '4096', 'billing_reviewed': '1',
    })
    assert saved.status_code == 302
    page = BeautifulSoup(client.get(path).text, 'html.parser')
    assert page.select_one('input[name=billing_input_limit]')['value'] == '1024'
    assert page.select_one('input[name=billing_output_limit]')['value'] == '4096'
    assert LLMClient().translate('authorized billing') == 'Translated text'


def test_reservation_audit_keeps_actual_route_when_config_is_edited(db, llm_env, client, login):
    def edit_route(call):
        llm_env.config.model = 'replacement-model'
        llm_env.config.cost_per_1k_input = '9'
        db.session.commit()
    llm_env.provider.before = edit_route
    LLMClient().translate('frozen request')
    login('admin')
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    row = page.select_one('[data-reservation-state=settled]')
    assert 'synthetic/primary' in row.get_text()
    assert 'replacement-model' not in row.get_text()
    assert '0.002000' in row.get_text()


def test_admin_can_audit_unknown_cost_and_reconcile_final_supplier_charge(app, client, login, csrf_token, llm_env):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    llm_env.provider.error = TimeoutError('reply lost')
    with pytest.raises(TimeoutError):
        LLMClient().translate('lost response')
    login('admin')
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    row = page.select_one('[data-reservation-state=unknown]')
    assert row is not None
    assert '0.092160' in row.get_text()
    form = row.select_one('form')
    result = client.post(form['action'], data={
        'csrf_token': csrf_token('/admin/llm-usage'), 'expected_state': 'unknown',
        'final_cost': '0.003', 'evidence_note': 'Synthetic final invoice #1',
        'confirmed_final': '1', 'confirmed_stopped': '1',
    })
    assert result.status_code == 302
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    row = page.select_one('[data-reservation-state=reconciled]')
    assert row is not None and '0.003000' in row.get_text()
    assert 'Synthetic final invoice #1' in row.get_text()
    llm_env.provider.error = None
    assert LLMClient().translate('after reconciliation') == 'Translated text'


def test_settled_usage_is_charged_once_not_again_via_usage_log(app, llm_env):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.095
    assert LLMClient().translate('first') == 'Translated text'
    assert LLMClient().translate('second') == 'Translated text'
    with pytest.raises(RuntimeError, match='budget exceeded'):
        LLMClient().translate('third')
    assert len(llm_env.provider.calls) == 2


@pytest.mark.parametrize('legacy_cost', [None, '0.009000'])
def test_legacy_unknown_or_spent_balance_is_not_silently_ignored(app, db, llm_env, legacy_cost):
    app.config['LLM_DAILY_BUDGET_USD'] = 0.10
    db.session.add(LLMUsageLog(config_id=llm_env.config.id, task_type='translate', cost_usd=legacy_cost, success=False))
    db.session.commit()
    with pytest.raises(RuntimeError):
        LLMClient().translate('new call')
    assert llm_env.provider.calls == []


def test_valid_cached_result_needs_no_new_paid_permit(app, llm_env):
    assert LLMClient().translate('cached input') == 'Translated text'
    app.config['LLM_DAILY_BUDGET_USD'] = 0.000001
    assert LLMClient().translate('cached input') == 'Translated text'
    assert len(llm_env.provider.calls) == 1
