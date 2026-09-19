"""Admin intent → actual producer/consumer, synthetic HTTP/SDK/broker only."""
import json
import re
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.startup_source import StartupSource
from app.models.llm import LLMConfig, LLMReservation

URL = 'https://directory.example.test/portfolio'
RESULT = {
    'website': 'https://alpine.example.test', 'overview': 'Synthetic company analysis',
    'founders': '', 'spinoff_source': '', 'core_tech': 'Sensors',
    'competitors': [], 'cn_competitor_names': '', 'business_status': '', 'recommendation': '持续监控',
    'recommendation_reason': 'Synthetic evidence',
}


@pytest.fixture
def discovery(app, client, fetch_network, monkeypatch, login, csrf_token):
    from celery import Celery
    from app.llm import client as provider
    from app.llm import circuit_breaker

    db.session.add(LLMConfig(
        provider='openai', model='synthetic-model',
        tasks=['company_analysis'], is_active=True, is_default=False,
        max_tokens=300, billing_input_limit=4000, billing_output_limit=500,
        cost_per_1k_input='0.001', cost_per_1k_output='0.002',
    ))
    db.session.commit()
    assert login('admin').status_code == 302
    sent, calls = [], []
    # Patch the class descriptor, not an instance-bound method: monkeypatch
    # undo on an instance would leave an attribute shadowing later class mocks.
    monkeypatch.setattr(Celery, 'send_task', lambda self, name, args=None, kwargs=None, **kw:
                        sent.append((name, args, kw)))
    monkeypatch.setattr(provider, 'redis_client', None)
    monkeypatch.setattr(circuit_breaker, 'redis_client', None)

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(RESULT)))],
        )

    monkeypatch.setattr(provider.litellm, 'completion', completion)
    fetch_network.configure(routes={URL: {'body': '<div data-name="Alpine Synthetic" '
                                             'data-description="Synthetic sensor company"></div>'}})
    return SimpleNamespace(client=client, csrf=csrf_token, sent=sent, calls=calls, network=fetch_network,
                           complete=completion, provider=provider)


def add_source(flow, **values):
    form = {'name': 'Synthetic directory', 'url': URL, 'source_type': 'startup', 'is_active': 'on'}
    form.update(values)
    form['csrf_token'] = flow.csrf('/admin/startup-sources/new')
    assert flow.client.post('/admin/startup-sources/new', data=form).status_code == 302
    return db.session.query(StartupSource).order_by(StartupSource.id.desc()).first().id


def scan(flow):
    from app.crawlers.startup_discovery import scan_startup_sources
    assert flow.client.post('/admin/startup-sources/scan-now', data={
        'csrf_token': flow.csrf('/admin/startup-sources')}).status_code == 302
    assert flow.sent.pop(0)[0] == scan_startup_sources.name
    scan_startup_sources.run()
    db.session.remove()


def jobs(flow):
    page = flow.client.get('/admin/startup-sources')
    assert page.status_code == 200
    return re.findall(rb'data-analysis-id="([a-f0-9-]+)"', page.data)


def test_scan_owns_only_new_company_and_defers_llm(discovery):
    old = Company(name='Historical company', slug='historical-company', is_grenoble=True,
                  ai_analysis_failures=3)
    db.session.add(old)
    db.session.commit()
    add_source(discovery)
    scan(discovery)
    assert db.session.query(Company).filter_by(name='Alpine Synthetic').count() == 1
    assert not discovery.calls, 'Crawl consumer must not invoke the model'
    assert db.session.query(Company).filter_by(slug='historical-company').one().ai_analysis_failures == 3
    identities = jobs(discovery)
    assert len(identities) == 1
    assert discovery.sent == [('app.llm.startup_tasks.analyze', [identities[0].decode()], {'queue': 'llm'})]
    assert b'queued' in discovery.client.get('/admin/startup-sources').data
    from app.llm.startup_tasks import analyze
    analyze.run(identities[0].decode())
    analyze.run(identities[0].decode())
    db.session.remove()
    assert len(discovery.calls) == 1
    company = db.session.query(Company).filter_by(name='Alpine Synthetic').one()
    assert company.ai_analysis['overview'] == RESULT['overview']
    assert db.session.query(LLMReservation).one().startup_analysis_id == identities[0].decode()
    assert b'succeeded' in discovery.client.get('/admin/startup-sources').data
    discovery.sent.clear()
    scan(discovery)
    assert len(jobs(discovery)) == 1
    assert not discovery.sent
    assert len(discovery.calls) == 1
