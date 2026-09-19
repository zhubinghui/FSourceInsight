"""Audit visibility and input/attempt rejection through public seams."""
import time

import pytest
from sqlalchemy import event, text

from app.extensions import db
from app.models import LLMConfig, LLMReservation
from app.llm.startup_tasks import analyze
from tests.test_crawlers import test_startup_analysis as base
from tests.test_crawlers.test_startup_reliability import prepared, state

discovery = base.discovery


def test_accounting_link_can_select_its_job_and_reject_unknown_identity(discovery):
    _, identity = prepared(discovery)
    analyze.run(identity)
    page = discovery.client.get('/admin/llm-usage')
    assert f'analysis_id={identity}' in page.text
    assert identity in discovery.client.get('/admin/startup-sources', query_string={'analysis_id': identity}).text
    assert discovery.client.get('/admin/startup-sources', query_string={'analysis_id': 'unknown'}).status_code == 404


@pytest.mark.parametrize('field,value', [
    ('input_hash', '0' * 64), ('prompt_hash', '0' * 64), ('protocol', 'old-protocol'),
    ('expires_at', '2099-01-01 00:00:00'), ('inputs', 'null'),
])
def test_inconsistent_persistent_input_is_not_payment_authority(discovery, field, value):
    _, identity = prepared(discovery)
    with db.engine.begin() as conn:
        conn.execute(text(f'UPDATE startup_analysis_job SET {field}=:value WHERE id=:id'), {'value': value, 'id': identity})
    analyze.run(identity)
    assert state(discovery, identity) == 'stale'
    assert not discovery.calls and db.session.query(LLMReservation).count() == 0


def test_unknown_usage_stops_even_an_available_fallback(discovery, monkeypatch):
    _, identity = prepared(discovery)
    db.session.add(LLMConfig(provider='fallback', model='available', tasks=['company_analysis'],
                            priority=200, max_tokens=300, billing_input_limit=4000,
                            billing_output_limit=500, cost_per_1k_input='0.001', cost_per_1k_output='0.002'))
    db.session.commit()

    def uncertain(**kwargs):
        result = discovery.complete(**kwargs)
        result.usage = None
        return result

    monkeypatch.setattr(discovery.provider.litellm, 'completion', uncertain)
    analyze.run(identity)
    analyze.run(identity)
    assert len(discovery.calls) == 1
    assert state(discovery, identity) == 'blocked'
    assert db.session.query(LLMReservation).one().state == 'unknown'


def test_untrusted_directory_name_is_escaped_in_admin_audit(discovery):
    body = '<div data-name="&lt;img src=x onerror=alert(1)&gt;" data-description="Synthetic"></div>'
    discovery.network.configure(routes={base.URL: {'body': body}})
    base.add_source(discovery)
    base.scan(discovery)
    page = discovery.client.get('/admin/startup-sources')
    assert len(base.jobs(discovery)) == 1
    assert '<img src=x onerror=alert(1)>' not in page.text
    assert '&lt;img src=x onerror=alert(1)&gt;' in page.text


@pytest.mark.parametrize('checkpoint', ['admission', 'application'])
def test_blocking_authority_reads_cannot_cross_the_final_deadline_checkpoint(discovery, monkeypatch, checkpoint):
    from app.models import Company
    _, identity = prepared(discovery)
    clock = time.time()
    phase = {'armed': checkpoint == 'admission', 'fired': False}

    def provider(**kwargs):
        phase['armed'] = True
        return discovery.complete(**kwargs)

    def slow_read(conn, cursor, statement, parameters, context, many):
        table = 'llm_config' if checkpoint == 'admission' else 'company'
        if phase['armed'] and not phase['fired'] and f'WHERE {table}.id =' in statement and statement.lstrip().startswith('SELECT'):
            phase['fired'] = True
            monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 181)

    monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    event.listen(db.engine, 'after_cursor_execute', slow_read)
    try:
        analyze.run(identity)
    finally:
        event.remove(db.engine, 'after_cursor_execute', slow_read)
    assert phase['fired'], 'Must exercise a blocking DB read at the production checkpoint'
    assert state(discovery, identity) == 'blocked'
    assert len(discovery.calls) == int(checkpoint == 'application')
    db.session.remove()
    assert db.session.query(Company).one().ai_analysis is None
    assert db.session.query(LLMReservation).count() == int(checkpoint == 'application')


def test_public_client_cannot_substitute_other_company_messages_during_a_claim(discovery, monkeypatch):
    from app.llm.client import LLMClient
    from app.llm.budget import BudgetError
    _, identity = prepared(discovery)

    def provider(**kwargs):
        with pytest.raises(BudgetError):
            LLMClient().analyze_company(name='Unrelated company', discovery_job=identity)
        return discovery.complete(**kwargs)

    monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    analyze.run(identity)
    assert state(discovery, identity) == 'succeeded'
    assert len(discovery.calls) == 1
