"""Only real Admin creation/retry/validation grants these M3 actor references."""
import pytest

from app.models.user import User
from app.models.crawl_learning import CrawlRepairSession, CrawlRepairRetry, CrawlValidationReport
from tests.test_web import test_crawl_learning as base
from tests.test_web import test_crawl_validation as validation

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


def sign_in(client, csrf_token, name):
    client.get('/auth/logout')
    assert client.post('/auth/login', data={'email': f'{name}@test.invalid', 'password': 'original-password',
        'csrf_token': csrf_token()}).status_code == 302


@pytest.mark.parametrize('action_kind', ['create', 'retry', 'validate'])
def test_learning_audit_actor_cannot_be_deleted(
        app, db, client, csrf_token, source, fetch_network, evidence_dir, learning_io, model, action_kind):
    actor = db.session.query(User).filter_by(email='owner@test.invalid').one()
    actor_id = actor.id
    actor.is_admin = True
    db.session.commit()
    if action_kind == 'validate':
        item = validation.learned(client, source, csrf_token, fetch_network, learning_io, model)
        validation.capture(client, item.base, fetch_network, 'holdout')
        location = item.location
        sign_in(client, csrf_token, 'owner')
        action, fields = base.form_at(client, location, 'form[data-validation-start]')
        assert client.post(action, data=fields).status_code == 302
    else:
        report, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
        if action_kind == 'create':
            sign_in(client, csrf_token, 'owner')
            action, fields = base.form_at(client, report, 'form[data-learning-start]')
        started = client.post(action, data=fields)
        assert started.status_code == 302
        location = started.location
        if action_kind == 'retry':
            app.config['LLM_DAILY_BUDGET_USD'] = '0.01'
            base.deliver(learning_io)
            sign_in(client, csrf_token, 'owner')
            action, fields = base.form_at(client, location, 'form[data-learning-retry]')
            fields['note'] = 'Reviewed synthetic unadmitted attempt'
            assert client.post(action, data=fields).status_code == 302
    db.session.remove()
    actor_model, column = {
        'create': (CrawlRepairSession, 'created_by_id'),
        'retry': (CrawlRepairRetry, 'requested_by_id'),
        'validate': (CrawlValidationReport, 'requested_by_id'),
    }[action_kind]
    assert getattr(db.session.query(actor_model).one(), column) == actor_id
    sign_in(client, csrf_token, 'admin')
    response = client.post(f'/admin/users/{actor_id}/delete', data={'csrf_token': csrf_token('/admin/users')})
    assert response.status_code == 302
    db.session.remove()
    assert db.session.get(User, actor_id) is not None
    assert getattr(db.session.query(actor_model).one(), column) == actor_id
    assert client.get(location).status_code == 200
