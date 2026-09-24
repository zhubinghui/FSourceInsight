"""Company AI Refresh through real admin HTTP → llm task; only SDK/broker/network/time are synthetic."""
import json
import re
import time
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.llm import LLMConfig, LLMReservation
from tests.test_crawlers import conftest as network_fixtures

fetch_network = network_fixtures.fetch_network

SLUG = 'alpine-synthetic'
SITE = 'https://alpine.example.test/'
OLD = {'website': SITE, 'overview': 'Old overview', 'core_tech': 'Old tech', 'competitors': []}
RESULT = {
    'website': SITE, 'overview': 'Fresh overview', 'founders': '', 'spinoff_source': '',
    'core_tech': 'Fresh sensors', 'competitors': [], 'cn_competitor_names': '', 'business_status': '',
    'recommendation': '持续监控', 'recommendation_reason': 'Synthetic evidence',
}
PAGE = '<html><body><p>' + 'Alpine Synthetic builds industrial sensors in Grenoble. ' * 10 + '</p></body></html>'


@pytest.fixture
def refresh(app, client, fetch_network, monkeypatch, login, csrf_token):
    from celery import Celery
    from app.llm import client as provider
    from app.llm import circuit_breaker
    from sqlalchemy import event

    @event.listens_for(db.engine, 'connect')
    def mysql_dialect_functions(connection, record):
        # The company page's weekly trend uses MySQL YEARWEEK; emulate the
        # database dialect boundary only (Sunday-first week, as MySQL mode 0).
        connection.create_function('yearweek', 1, lambda value: value and int(
            __import__('datetime').datetime.fromisoformat(value).strftime('%Y%U')))

    db.engine.dispose()
    db.session.add(LLMConfig(
        provider='openai', model='synthetic-model', tasks=['company_analysis'], is_active=True,
        is_default=False, max_tokens=300, billing_input_limit=4000, billing_output_limit=500,
        cost_per_1k_input='0.001', cost_per_1k_output='0.002'))
    db.session.add(Company(name='Alpine Synthetic', slug=SLUG, website=SITE, ai_analysis=dict(OLD)))
    db.session.commit()
    assert login('admin').status_code == 302
    flow = SimpleNamespace(client=client, csrf=csrf_token, sent=[], calls=[], before=None, error=None,
                           broker_error=None, network=fetch_network)

    def send_task(self, name, args=None, kwargs=None, **options):
        if flow.broker_error:
            raise flow.broker_error
        flow.sent.append((name, args, options))

    def completion(**kwargs):
        flow.calls.append(kwargs)
        if flow.before:
            flow.before(kwargs)
        if flow.error:
            raise flow.error
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(RESULT)))])

    monkeypatch.setattr(Celery, 'send_task', send_task)
    monkeypatch.setattr(provider, 'redis_client', None)
    monkeypatch.setattr(circuit_breaker, 'redis_client', None)
    monkeypatch.setattr(provider.litellm, 'completion', completion)
    fetch_network.configure(routes={SITE: {'body': PAGE}})
    return flow


def request_refresh(flow):
    page = f'/companies/{SLUG}'
    response = flow.client.post(f'{page}/generate-analysis', data={'csrf_token': flow.csrf(page)},
                                follow_redirects=True)
    assert response.status_code == 200
    return response.data


def detail(flow):
    response = flow.client.get(f'/companies/{SLUG}')
    assert response.status_code == 200
    return response.data


def latest(flow):
    found = re.search(rb'data-refresh-id="([a-f0-9-]+)" data-refresh-state="([a-z_]+)"', detail(flow))
    assert found, 'Company page must show the latest refresh job'
    return found.group(1).decode(), found.group(2).decode()


def run(identity):
    from app.llm.refresh_tasks import refresh as task
    task.run(identity)
    db.session.remove()


def company():
    return db.session.query(Company).filter_by(slug=SLUG).one()


def test_repeated_requests_share_one_job_and_one_paid_call(refresh):
    request_refresh(refresh)
    body = request_refresh(refresh)
    assert b'already' in body
    identity, state = latest(refresh)
    assert state == 'queued'
    assert refresh.sent == [('app.llm.refresh_tasks.refresh', [identity], {'queue': 'llm'})]
    run(identity)
    run(identity)
    assert len(refresh.calls) == 1
    assert PAGE[20:80] in refresh.calls[0]['messages'][-1]['content'], 'Homepage excerpt reaches the model'
    assert company().ai_analysis['overview'] == 'Fresh overview'
    assert company().ai_revision_history[-1]['source'] == 'ai-refresh-website'
    assert db.session.query(LLMReservation).one().company_refresh_id == identity
    assert latest(refresh) == (identity, 'succeeded')
    refresh.sent.clear()
    request_refresh(refresh)
    again, state = latest(refresh)
    assert again != identity and state == 'queued'
    assert refresh.sent == [('app.llm.refresh_tasks.refresh', [again], {'queue': 'llm'})]


def test_manual_edit_during_refresh_is_never_overwritten(refresh):
    request_refresh(refresh)
    identity, _ = latest(refresh)
    edit = f'/companies/{SLUG}/edit-analysis'

    def admin_edits(call):
        response = refresh.client.post(edit, data={
            'csrf_token': refresh.csrf(edit), 'overview': 'Operator reviewed overview', 'website': SITE})
        assert response.status_code == 302

    refresh.before = admin_edits
    run(identity)
    assert len(refresh.calls) == 1
    assert company().ai_analysis['overview'] == 'Operator reviewed overview'
    assert company().ai_revision_history[-1]['source'] == 'manual-edit'
    assert latest(refresh) == (identity, 'stale')
    assert db.session.query(LLMReservation).one().state == 'settled', 'Paid usage is kept, not erased'


def test_provider_failure_blocks_without_automatic_paid_retry(refresh):
    request_refresh(refresh)
    identity, _ = latest(refresh)
    refresh.error = RuntimeError('PRIVATE_PROVIDER_DETAIL')
    run(identity)  # Must not raise a Celery retry that pays again.
    run(identity)
    assert len(refresh.calls) == 1
    assert company().ai_analysis == OLD
    assert latest(refresh) == (identity, 'blocked')
    assert b'PRIVATE_PROVIDER_DETAIL' not in detail(refresh)
    refresh.error, refresh.sent[:] = None, []
    request_refresh(refresh)
    again, state = latest(refresh)
    assert again != identity and state == 'queued'
    run(again)
    assert company().ai_analysis['overview'] == 'Fresh overview'


def test_result_after_the_deadline_is_not_applied(refresh, monkeypatch):
    request_refresh(refresh)
    identity, _ = latest(refresh)
    clock = time.time()
    refresh.before = lambda call: monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 181)
    run(identity)
    assert company().ai_analysis == OLD
    assert latest(refresh) == (identity, 'blocked')


def test_broker_loss_keeps_intent_for_bounded_recovery(refresh, monkeypatch):
    from app.llm.refresh_tasks import recover
    refresh.broker_error = RuntimeError('PRIVATE_BROKER_PAYLOAD')
    body = request_refresh(refresh)
    assert b'PRIVATE_BROKER_PAYLOAD' not in body
    identity, state = latest(refresh)
    assert state == 'queued' and not refresh.sent
    refresh.broker_error = None
    recover.run()
    assert not refresh.sent, 'Redispatch keeps its minimum interval'
    clock = time.time()
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 121)
    recover.run()
    assert refresh.sent == [('app.llm.refresh_tasks.refresh', [identity], {'queue': 'llm'})]
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 86401)
    recover.run()
    db.session.remove()
    assert latest(refresh) == (identity, 'blocked')
    run(identity)
    assert not refresh.calls


def test_legacy_company_id_message_never_pays(refresh):
    from app.llm.tasks import refresh_company_analysis
    refresh_company_analysis.run(company().id)
    assert not refresh.calls
    assert company().ai_analysis == OLD


def test_non_admin_cannot_queue_refresh(refresh, app, users):
    from bs4 import BeautifulSoup
    owner = app.test_client()
    form = BeautifulSoup(owner.get('/auth/login').text, 'html.parser')
    assert owner.post('/auth/login', data={
        'email': users['owner'].email, 'password': 'original-password',
        'csrf_token': form.select_one('input[name=csrf_token]')['value']}).status_code == 302
    page = owner.get(f'/companies/{SLUG}')
    assert page.status_code == 200 and b'generate-analysis' not in page.data
    token = BeautifulSoup(owner.get('/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')
    owner.post(f'/companies/{SLUG}/generate-analysis', data={'csrf_token': token['value'] if token else ''})
    assert not refresh.sent
    assert b'data-refresh-id' not in detail(refresh)


def test_model_supplied_private_website_is_not_stored_as_next_fetch_target(refresh, monkeypatch):
    import tests.test_web.test_company_refresh as module
    monkeypatch.setitem(module.RESULT, 'website', 'http://127.0.0.1:8080/admin')
    request_refresh(refresh)
    identity, _ = latest(refresh)
    run(identity)
    assert company().ai_analysis['website'] == SITE
    assert company().ai_analysis['overview'] == 'Fresh overview'
