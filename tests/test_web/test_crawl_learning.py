"""Learning through Admin HTTP; only transport/time/storage faults are substituted."""
import json
from types import SimpleNamespace
import pytest
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_policy as policy

source = policy.source
fetch_network = policy.fetch_network
evidence_dir = policy.evidence_dir


@pytest.fixture
def learning_io(app, monkeypatch):
    app.config['CRAWL_LEARNING_ENABLED'] = True
    sent = []
    monkeypatch.setattr('celery.app.base.Celery.send_task', lambda self, name, args=None, **kw: sent.append((name, args)))
    def forbidden(**kwargs):
        raise AssertionError('Admin start must not call a model')
    monkeypatch.setattr('litellm.completion', forbidden)
    return sent


def form_at(client, location, selector):
    response = client.get(location)
    assert response.status_code == 200
    form = BeautifulSoup(response.text, 'html.parser').select_one(selector)
    assert form is not None
    return form['action'], {node['name']: node.get('value', '') for node in form.select('input[name]')}


def prepared(client, source, csrf_token, fetch_network):
    policy.save_policy(client, source)
    _, report = policy.captured_preview(client, source, csrf_token, fetch_network)
    return report, form_at(client, report, 'form[data-learning-start]')


def test_start_records_one_cancellable_session_without_inline_model_or_ingestion(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io):
    report, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    requests = len(fetch_network.events())
    started = client.post(action, data=fields)
    assert started.status_code == 302
    with app.app_context():
        response = client.get(started.location)
        page = BeautifulSoup(response.text, 'html.parser')
        assert page.select_one('[data-learning-state]').get_text(strip=True) == 'queued'
        assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '0 / 3'
        config_page = BeautifulSoup(client.get(f'/admin/sources/{source}/crawl-config').text, 'html.parser')
        assert config_page.select_one(f'a[data-learning-session][href="{started.location}"]')
        assert page.select_one('[data-learning-limit]').get_text(strip=True) == '0.200000'
        assert 'Not independently validated' in page.get_text()
        assert response.headers['Cache-Control'] == 'no-store'
        assert client.post(action, data=fields).location == started.location
        assert client.get('/api/v1/news').json['total'] == 0
        cancel, data = form_at(client, started.location, 'form[data-learning-cancel]')
        assert client.post(cancel, data=data).status_code == 302
        assert BeautifulSoup(client.get(started.location).text, 'html.parser').select_one('[data-learning-state]').get_text(strip=True) == 'cancelled'
        assert client.post(action, data=fields).location == started.location
    assert len(fetch_network.events()) == requests
    assert learning_io and all(name == 'app.crawlers.learning_tasks.learn' for name, _ in learning_io)


@pytest.fixture
def model(app, db, monkeypatch, learning_io):
    from app.models import LLMConfig
    from tests.test_llm.conftest import MemoryRedis, Provider
    provider, cache = Provider(), MemoryRedis()
    # Operator-reviewed: the synthetic provider bills a byte-level tokenizer.
    # 7168 x 0.01 + 1024 x 0.02 per 1k keeps the historical 0.092160 reservation.
    app.config['CRAWL_LEARNING_BYTE_BOUND_PROVIDERS'] = 'synthetic'
    config = LLMConfig(provider='synthetic', model='recipe', tasks=['crawl_schema'],
        is_default=False, cost_per_1k_input='0.01', cost_per_1k_output='0.02',
        billing_input_limit=7168, billing_output_limit=1024, max_tokens=1024)
    db.session.add(config)
    db.session.commit()
    monkeypatch.setattr('litellm.completion', provider)
    monkeypatch.setattr('app.llm.client.redis_client', cache)
    monkeypatch.setattr('app.llm.circuit_breaker.redis_client', cache)
    return SimpleNamespace(provider=provider, config=config, cache=cache)


def deliver(sent):
    from app.crawlers.learning_tasks import learn
    name, args = sent[-1]
    assert name == learn.name
    learn.run(*args)


def test_learning_saves_only_a_candidate_with_durable_round_and_cost_audit(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    from tests.test_web.test_crawl_config import recipe_for
    _, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    model.provider.reply = recipe_for(source)
    requests = len(fetch_network.events())
    deliver(learning_io)
    with app.app_context():
        page = BeautifulSoup(client.get(started.location).text, 'html.parser')
        assert page.select_one('[data-learning-state]').get_text(strip=True) == 'awaiting_validation'
        assert page.select_one('[data-learning-rounds]').get_text(strip=True) == '1 / 3'
        assert page.select_one('[data-learning-spent]').get_text(strip=True) == '0.002000'
        assert page.select_one('[data-learning-held]').get_text(strip=True) == '0.000000'
        candidate = client.get(page.select_one('a[data-learning-candidate]')['href'])
        assert json.loads(BeautifulSoup(candidate.text, 'html.parser').select_one('[data-recipe]').get_text()) == recipe_for(source)
        assert 'Candidate' in candidate.text
        assert 'Not independently validated' in page.get_text()
        assert client.get('/api/v1/news').json['total'] == 0
    deliver(learning_io)
    assert len(model.provider.calls) == 1
    assert len(fetch_network.events()) == requests


def test_session_budget_refuses_full_supplier_bound_before_payment(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    from tests.test_web.test_crawl_config import recipe_for
    model.config.cost_per_1k_input = '0.03'
    model.config.cost_per_1k_output = '0.06'
    db.session.commit()
    _, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    model.provider.reply = recipe_for(source)
    deliver(learning_io)
    assert not model.provider.calls
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert 'Learning session budget exceeded' in page.get_text()
    assert page.select_one('[data-learning-state]').get_text(strip=True) == 'blocked'
    assert page.select_one('[data-learning-held]').get_text(strip=True) == '0.000000'


def state(client, location):
    return BeautifulSoup(client.get(location).text, 'html.parser').select_one('[data-learning-state]').get_text(strip=True)


@pytest.mark.parametrize('change', ['disabled', 'revoke', 'source_aba', 'missing_evidence', 'capture_gap', 'old_protocol'])
def test_changed_authority_prevents_claim_and_payment(
        db, app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, change):
    from sqlalchemy import text
    _, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    if change == 'disabled':
        app.config['CRAWL_LEARNING_ENABLED'] = False
    elif change == 'revoke':
        revoke, data = policy.revoke_form(client, source)
        assert client.post(revoke, data=data).status_code == 302
    elif change == 'source_aba':
        for _ in range(2):
            assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    elif change == 'missing_evidence':
        next(evidence_dir.glob('*.json')).unlink()
    elif change == 'capture_gap':
        with db.engine.begin() as conn:
            conn.execute(text('DELETE FROM crawl_capture_manifest'))
    else:
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE crawl_repair_session SET protocol_version='old-protocol'"))
    deliver(learning_io)
    assert not model.provider.calls
    assert state(client, started.location) == 'blocked'


@pytest.mark.parametrize('change', ['cancel', 'revoke', 'source_aba'])
def test_permission_changes_during_provider_call_discard_candidate_but_settle_cost(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, change):
    from tests.test_web.test_crawl_config import recipe_for
    _, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    def during_call(kwargs):
        # HTTP can commit while the provider is in flight: no business lock held.
        page = BeautifulSoup(client.get(started.location).text, 'html.parser')
        assert page.select_one('[data-learning-held]').get_text(strip=True) == '0.092160'
        if change == 'cancel':
            action, data = form_at(client, started.location, 'form[data-learning-cancel]')
            assert client.post(action, data=data).status_code == 302
        elif change == 'revoke':
            action, data = policy.revoke_form(client, source)
            assert client.post(action, data=data).status_code == 302
        else:
            for _ in range(2):
                client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()})
        deliver(learning_io)  # Duplicate delivery while the original is in flight.
    model.provider.before = during_call
    model.provider.reply = recipe_for(source)
    deliver(learning_io)
    page = BeautifulSoup(client.get(started.location).text, 'html.parser')
    assert state(client, started.location) == ('cancelled' if change == 'cancel' else 'blocked')
    assert ('discarded' if change == 'cancel' else 'blocked') in page.select_one('[data-learning-attempt]').get_text()
    assert page.select_one('[data-learning-spent]').get_text(strip=True) == '0.002000'
    assert not page.select('a[data-learning-candidate]')
    assert len(model.provider.calls) == 1
    assert client.get('/api/v1/news').json['total'] == 0


@pytest.mark.parametrize('scope', ['LLM_DAILY_BUDGET_USD', 'CRAWL_LEARNING_DAILY_BUDGET_USD',
                                 'CRAWL_LEARNING_SOURCE_DAILY_BUDGET_USD'])
def test_global_agent_and_source_budgets_include_prior_sessions(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, scope):
    from tests.test_web.test_crawl_config import recipe_for
    # One actual charge 0.002 plus the next bound 0.09216 exceeds 0.093.
    app.config[scope] = '0.093'
    model.provider.reply = recipe_for(source)
    _, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    first = client.post(action, data=fields)
    deliver(learning_io)
    assert state(client, first.location) == 'awaiting_validation'
    _, report = policy.captured_preview(client, source, csrf_token, fetch_network)
    action, fields = form_at(client, report, 'form[data-learning-start]')
    second = client.post(action, data=fields)
    deliver(learning_io)
    assert state(client, second.location) == 'blocked'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('problem', ['no_assignment', 'unknown_price', 'token_bound'])
def test_unapproved_or_unbounded_model_never_receives_learning_inputs(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, problem):
    if problem == 'no_assignment':
        model.config.tasks, model.config.is_default = ['translate'], True
    elif problem == 'unknown_price':
        model.config.billing_input_limit = None
    else:
        model.config.billing_input_limit = 20000  # Plus output cannot fit 20,000 total.
        model.config.cost_per_1k_input = model.config.cost_per_1k_output = '0'
    db.session.commit()
    _, (action, fields) = prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    deliver(learning_io)
    assert not model.provider.calls
    assert state(client, started.location) == 'blocked'
