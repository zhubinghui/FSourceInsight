"""Actual safe-fetch transport, source ownership, admin visibility and routing."""
import json
import time

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import Company, LLMConfig, LLMReservation
from app.llm.startup_tasks import analyze, recover
from tests.test_crawlers import test_startup_analysis as base
from tests.test_crawlers.test_startup_reliability import prepared, state

discovery = base.discovery


@pytest.mark.parametrize('aliases', [None, ['Alpine Synthetic']])
def test_legacy_null_or_known_alias_preserves_ownership(discovery, aliases):
    db.session.add(Company(name='Legacy', slug='legacy', aliases=aliases, is_grenoble=True,
                           ai_analysis_failures=3))
    db.session.commit()
    base.add_source(discovery)
    base.scan(discovery)
    expected = int(aliases is None)
    assert len(base.jobs(discovery)) == expected
    assert db.session.query(Company).count() == 1 + expected
    assert db.session.query(Company).filter_by(slug='legacy').one().ai_analysis_failures == 3
    assert not discovery.calls


@pytest.mark.parametrize('refusal', ['private', 'robots', 'redirect', 'too-large'])
def test_directory_safety_refusal_has_no_direct_fallback_or_llm(discovery, refusal, caplog):
    url = base.URL if refusal != 'private' else 'http://127.0.0.1/private?secret=PRIVATE_URL'
    routes = {
        'robots': {'https://directory.example.test/robots.txt': {'body': 'User-agent: *\nDisallow: /'}},
        'redirect': {base.URL: {'status': 302, 'headers': {'Location': 'https://unapproved.example.test/private?secret=PRIVATE_URL'}}},
        'too-large': {base.URL: {'body': 'x' * (512 * 1024 + 1)}},
        'private': {},
    }[refusal]
    discovery.network.configure(routes=routes)
    base.add_source(discovery, url=url)
    base.scan(discovery)
    assert not base.jobs(discovery) and not discovery.sent and not discovery.calls
    assert db.session.query(Company).count() == 0
    assert all(e['host'] != 'unapproved.example.test' for e in discovery.network.events() if e['kind'] == 'dns')
    assert 'PRIVATE_URL' not in caplog.text


def test_per_source_creation_is_bounded_and_does_not_adopt_other_source_work(discovery):
    body = ''.join(f'<div data-name="Synthetic {n}" data-description="Synthetic sensors"></div>' for n in range(30))
    discovery.network.configure(routes={base.URL: {'body': body}})
    base.add_source(discovery)
    base.scan(discovery)
    assert len(base.jobs(discovery)) == 20
    assert len(discovery.sent) == 20 and not discovery.calls
    discovery.sent.clear()
    base.add_source(discovery, name='Other source')
    base.scan(discovery)
    assert len(base.jobs(discovery)) == 30
    assert len(discovery.sent) == 10 and not discovery.calls
    assert len({args[0] for _, args, _ in discovery.sent}) == 10


def test_one_source_write_failure_cannot_commit_its_partial_companies_with_next_source(discovery):
    from app.models.startup_source import StartupSource
    other = 'https://directory2.example.test/portfolio'
    discovery.network.configure(routes={
        base.URL: {'body': '<div data-name="Partial" data-description="Synthetic"></div>'
                          '<div data-name="Broken" data-description="Synthetic"></div>'},
        other: {'body': '<div data-name="Good Startup" data-description="Synthetic"></div>'},
    })
    failed_id = base.add_source(discovery)
    good_id = base.add_source(discovery, url=other, name='Good', source_type='startup')
    with db.engine.begin() as conn:
        conn.exec_driver_sql("CREATE TRIGGER fail_second BEFORE INSERT ON startup_analysis_job WHEN json_extract(NEW.inputs, '$.company.name') = 'Broken' BEGIN SELECT RAISE(FAIL, 'PRIVATE_PARTIAL_SQL'); END")
    base.scan(discovery)
    assert len(base.jobs(discovery)) == 1 and len(discovery.sent) == 1
    assert db.session.query(Company).count() == 1
    company = db.session.query(Company).one()
    assert (company.name, company.company_stage, company.sector) == ('Good Startup', 'startup', None)
    assert db.session.get(StartupSource, failed_id).last_scanned_at is None
    assert db.session.get(StartupSource, good_id).last_scanned_at is not None
    assert not discovery.calls


def test_valid_cache_is_free_for_a_current_claimed_job(discovery, monkeypatch):
    from app.llm.client import LLMClient
    from tests.test_llm.conftest import MemoryRedis
    _, identity = prepared(discovery)
    cache = MemoryRedis()
    monkeypatch.setattr(discovery.provider, 'redis_client', cache)
    # Ordinary public method primes precisely the same effective input.
    LLMClient().analyze_company(name='Alpine Synthetic', description='Synthetic sensor company', company_stage='startup')
    assert len(discovery.calls) == 1
    analyze.run(identity)
    assert state(discovery, identity) == 'succeeded'
    assert len(discovery.calls) == 1
    assert db.session.query(LLMReservation).filter_by(startup_analysis_id=identity).count() == 0


@pytest.mark.parametrize('valid_at', [2, None])
def test_malformed_paid_responses_have_bounded_fallbacks(discovery, monkeypatch, valid_at):
    _, identity = prepared(discovery)
    for number in range(2, 6):
        db.session.add(LLMConfig(provider=f'synthetic{number}', model='fallback', tasks=['company_analysis'],
                                priority=number + 100, max_tokens=300, billing_input_limit=4000,
                                billing_output_limit=500, cost_per_1k_input='0.001', cost_per_1k_output='0.002'))
    db.session.commit()

    def provider(**kwargs):
        response = discovery.complete(**kwargs)
        if len(discovery.calls) != valid_at:
            response.choices[0].message.content = 'not-json'
        return response

    monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    analyze.run(identity)
    assert len(discovery.calls) == (valid_at or 3)
    assert state(discovery, identity) == ('succeeded' if valid_at else 'blocked')
    rows = db.session.query(LLMReservation).filter_by(startup_analysis_id=identity).all()
    assert len(rows) == (valid_at or 3)
    assert all(row.state == 'settled' for row in rows)
    analyze.run(identity)
    assert len(discovery.calls) == (valid_at or 3)


def test_readiness_tasks_and_recovery_route_are_llm_only(discovery):
    from celery_app import celery
    assert 'app.llm.startup_tasks' in celery.conf.include
    assert celery.conf.task_routes['app.llm.startup_tasks.*']['queue'] == 'llm'
    assert analyze.acks_late and analyze.ignore_result
    schedule = celery.conf.beat_schedule['recover-startup-analysis']
    assert schedule == {'task': recover.name, 'schedule': 60.0}


@pytest.mark.parametrize('actor', ['owner', 'anonymous'])
def test_private_admin_history_requires_admin(discovery, actor):
    _, identity = prepared(discovery)
    if actor == 'anonymous':
        discovery.client.get('/auth/logout')
    else:
        assert discovery.client.post('/auth/login', data={
            'email': 'owner@test.invalid', 'password': 'original-password',
            'csrf_token': discovery.csrf(),
        }).status_code == 302
    response = discovery.client.get('/admin/startup-sources')
    assert response.status_code == 302
    assert identity not in response.text
    assert response.headers['Cache-Control'] == 'no-store'


def test_scan_csrf_and_broker_failure_do_not_claim_success(discovery, monkeypatch):
    from celery import Celery
    assert discovery.client.post('/admin/startup-sources/scan-now').status_code == 400
    assert not discovery.sent

    def broken(*args, **kwargs):
        raise RuntimeError('PRIVATE_SCAN_TRANSPORT')

    token = discovery.csrf('/admin/startup-sources')
    monkeypatch.setattr(Celery, 'send_task', broken)
    response = discovery.client.post('/admin/startup-sources/scan-now', data={'csrf_token': token})
    assert response.status_code == 503 and 'PRIVATE_SCAN' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'


def test_status_sql_failure_is_private_and_sanitized(discovery, caplog):
    prepared(discovery)

    def unavailable(conn, cursor, statement, parameters, context, many):
        if 'FROM startup_analysis_job' in statement:
            raise OperationalError(None, None, RuntimeError('PRIVATE_STATUS_SQL'))

    event.listen(db.engine, 'before_cursor_execute', unavailable)
    try:
        response = discovery.client.get('/admin/startup-sources')
    finally:
        event.remove(db.engine, 'before_cursor_execute', unavailable)
    assert response.status_code == 503
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'PRIVATE_STATUS_SQL' not in response.text + caplog.text


def test_recovery_backoff_does_not_hot_loop_a_lost_message(discovery, monkeypatch):
    _, identity = prepared(discovery)
    recover.run()
    assert not discovery.sent
    clock = time.time()
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 121)
    recover.run()
    assert discovery.sent == [(analyze.name, [identity], {'queue': 'llm'})]
    recover.run()
    assert len(discovery.sent) == 1


def test_dispatch_spacing_is_not_shortened_by_whole_second_storage(discovery, monkeypatch):
    clock = int(time.time()) + 1.5
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock)
    prepared(discovery)
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 119.9)
    recover.run()
    assert not discovery.sent
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 121)
    recover.run()
    assert len(discovery.sent) == 1


def test_unsafe_generated_website_never_reaches_public_company(discovery, monkeypatch):
    _, identity = prepared(discovery)

    def provider(**kwargs):
        response = discovery.complete(**kwargs)
        data = dict(base.RESULT, website='javascript:alert(1)')
        response.choices[0].message.content = json.dumps(data)
        return response

    monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    analyze.run(identity)
    assert state(discovery, identity) == 'blocked'
    assert db.session.query(Company).one().ai_analysis is None
    assert db.session.query(LLMReservation).one().state == 'settled'
