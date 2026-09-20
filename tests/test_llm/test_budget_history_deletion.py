"""Admin deletion cannot detach M3 accounting, even before usage is written."""
import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.llm.client import LLMClient
from app.models import LLMConfig, LLMReservation, LLMReconciliation
from app.models.user import User
from tests.test_llm.test_budget_admin import pending_form, correction


def test_config_with_an_inflight_reservation_cannot_be_deleted(
        db, client, login, csrf_token, llm_env):
    login('admin')
    config_id = llm_env.config.id
    observed = []
    def during_provider(kwargs):
        assert db.session.query(LLMReservation).one().state == 'reserved'
        response = client.post(f'/admin/llm-config/{config_id}/delete', data={
            'csrf_token': csrf_token('/admin/llm-config')})
        observed.append((response.status_code, db.session.get(LLMConfig, config_id) is not None))
    llm_env.provider.before = during_provider
    LLMClient().translate('synthetic accounting owner')
    assert observed == [(302, True)]
    assert db.session.query(LLMReservation).one().state == 'settled'


def test_reconciliation_actor_cannot_be_deleted_by_another_admin(
        db, client, login, csrf_token, llm_env):
    form = pending_form(client, login, llm_env)
    assert client.post(form['action'], data=correction(form)).status_code == 302
    actor_id = db.session.query(LLMReconciliation).one().actor_id
    db.session.query(User).filter_by(email='owner@test.invalid').one().is_admin = True
    db.session.commit()
    client.get('/auth/logout')
    assert client.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password',
        'csrf_token': csrf_token()}).status_code == 302
    response = client.post(f'/admin/users/{actor_id}/delete', data={'csrf_token': csrf_token('/admin/users')})
    assert response.status_code == 302
    assert db.session.get(User, actor_id) is not None
    row = db.session.query(LLMReconciliation).one()
    assert row.actor_id == actor_id and str(row.final_cost) == '0.003000'
    assert db.session.query(LLMReservation).one().state == 'reconciled'


@pytest.mark.parametrize('kind', ['user', 'llm_config'])
def test_delete_reference_race_rolls_back_without_private_errors(
        db, client, login, csrf_token, llm_env, kind):
    login('admin')
    model = User if kind == 'user' else LLMConfig
    row = db.session.query(User).filter_by(email='owner@test.invalid').one() if kind == 'user' else llm_env.config
    identity = row.id
    path = '/admin/users' if kind == 'user' else '/admin/llm-config'
    token = csrf_token(path)
    def collision(conn, cursor, statement, parameters, context, many):
        if statement.startswith(f'DELETE FROM {kind} '):
            raise IntegrityError('PRIVATE_REFERENCE_SQL', {}, RuntimeError('PRIVATE_REFERENCE_DETAIL'))
    event.listen(db.engine, 'before_cursor_execute', collision)
    try:
        response = client.post(f'{path}/{identity}/delete', data={'csrf_token': token}, follow_redirects=True)
    finally:
        event.remove(db.engine, 'before_cursor_execute', collision)
    assert response.status_code == 200
    assert 'PRIVATE_REFERENCE' not in response.text
    db.session.remove()
    assert db.session.get(model, identity) is not None
