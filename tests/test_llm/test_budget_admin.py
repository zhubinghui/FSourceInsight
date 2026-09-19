"""Billing review and final-charge corrections through real Admin HTTP."""
from bs4 import BeautifulSoup
import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import MultiDict

from app.llm.client import LLMClient


def pending_form(client, login, llm_env):
    llm_env.provider.error = TimeoutError('lost reply')
    with pytest.raises(TimeoutError):
        LLMClient().translate('accounting fixture')
    login('admin')
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    return page.select_one('[data-reservation-state=unknown] form')


def correction(form):
    return {'csrf_token': form.select_one('[name=csrf_token]')['value'],
            'expected_state': 'unknown', 'final_cost': '0.003',
            'evidence_note': 'Final test invoice', 'confirmed_final': '1', 'confirmed_stopped': '1'}


@pytest.mark.parametrize('change', [
    {'confirmed_final': '0'}, {'confirmed_stopped': '0'}, {'csrf_token': ''},
    {'final_cost': '-1'}, {'final_cost': 'NaN'}, {'final_cost': 'Infinity'},
    {'evidence_note': ''}, {'evidence_note': 'a' * 501}, {'expected_state': 'reserved'},
])
def test_reconciliation_requires_current_state_finite_amount_and_explicit_attestations(client, login, llm_env, change):
    form = pending_form(client, login, llm_env)
    data = correction(form)
    data.update(change)
    assert client.post(form['action'], data=data).status_code in {400, 409}
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    assert page.select_one('[data-reservation-state=unknown]') is not None
    assert page.select_one('[data-reservation-state=reconciled]') is None


def test_reconciliation_is_append_only_and_escapes_operator_notes(client, login, llm_env):
    form = pending_form(client, login, llm_env)
    data = correction(form)
    data['evidence_note'] = '<script>synthetic()</script>'
    assert client.post(form['action'], data=data).status_code == 302
    data.update(final_cost='0', evidence_note='overwrite')
    assert client.post(form['action'], data=data).status_code == 409
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    row = page.select_one('[data-reservation-state=reconciled]')
    assert '0.003000' in row.get_text() and '<script>synthetic()</script>' in row.get_text()
    assert row.select_one('script') is None and 'overwrite' not in row.get_text()


@pytest.mark.parametrize('identity', ['anonymous', 'owner'])
def test_nonadmin_cannot_review_or_release_budget(client, login, csrf_token, llm_env, identity):
    form = pending_form(client, login, llm_env)
    client.get('/auth/logout')
    if identity == 'owner':
        login('owner')
    data = correction(form)
    data['csrf_token'] = csrf_token('/auth/login')
    assert client.get('/admin/llm-usage').status_code == 302
    assert client.post(form['action'], data=data).status_code == 302
    login('admin')
    assert 'data-reservation-state="unknown"' in client.get('/admin/llm-usage').text


def test_reconciliation_sql_failure_keeps_hold_and_does_not_expose_private_parameters(db, client, login, llm_env):
    form = pending_form(client, login, llm_env)
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO llm_reconciliation '):
            raise OperationalError('PRIVATE_STATEMENT', {'secret': 'PRIVATE_PARAMETER'}, RuntimeError('offline'))
    event.listen(db.engine, 'before_cursor_execute', fail)
    try:
        response = client.post(form['action'], data=correction(form))
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail)
    assert response.status_code == 503
    assert 'PRIVATE_' not in response.text
    assert 'data-reservation-state="unknown"' in client.get('/admin/llm-usage').text


@pytest.mark.parametrize('changes', [
    {'billing_reviewed': ''}, {'billing_input_limit': '0'}, {'billing_output_limit': '100'},
    {'billing_input_limit': '1.5'}, {'billing_output_limit': ''}, {'cost_per_1k_input': '-1'},
    {'cost_per_1k_input': 'NaN'}, {'cost_per_1k_output': ''}, {'max_tokens': '0'},
])
def test_invalid_billing_edit_leaves_previous_reviewed_configuration_intact(client, login, csrf_token, llm_env, changes):
    login('admin')
    path = f'/admin/llm-config/{llm_env.config.id}/edit'
    data = {'csrf_token': csrf_token(path), 'provider': 'synthetic', 'model': 'replacement',
            'max_tokens': '4096', 'cost_per_1k_input': '0.01', 'cost_per_1k_output': '0.02',
            'billing_input_limit': '1024', 'billing_output_limit': '4096', 'billing_reviewed': '1'}
    data.update(changes)
    assert client.post(path, data=data).status_code == 400
    page = BeautifulSoup(client.get(path).text, 'html.parser')
    assert page.select_one('[name=model]')['value'] == 'primary'
    assert page.select_one('[name=billing_input_limit]')['value'] == '1024'


def test_accounting_audit_is_private_and_reports_unsettled_balance(client, login, llm_env):
    pending_form(client, login, llm_env)
    response = client.get('/admin/llm-usage')
    assert response.headers.get('Cache-Control') == 'no-store'
    assert response.headers.get('Referrer-Policy') == 'no-referrer'
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-unsettled-count]').get_text(strip=True) == '1'
    assert page.select_one('[data-unsettled-usd]').get_text(strip=True) == '0.092160'


def test_duplicate_billing_fields_are_not_silently_accepted(client, login, csrf_token, llm_env):
    login('admin')
    path = f'/admin/llm-config/{llm_env.config.id}/edit'
    data = MultiDict([('csrf_token', csrf_token(path)), ('provider', 'synthetic'), ('model', 'primary'),
                     ('billing_input_limit', '1024'), ('billing_input_limit', '9999')])
    assert client.post(path, data=data).status_code == 400
