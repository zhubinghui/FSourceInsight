"""Failure/race behavior through production tasks and real Admin HTTP."""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Company, LLMConfig, LLMReservation, StartupAnalysisJob
from app.models.startup_source import StartupSource
from app.llm.startup_tasks import analyze, recover
from tests.test_crawlers import test_startup_analysis as base

discovery = base.discovery


def prepared(flow):
    source_id = base.add_source(flow)
    base.scan(flow)
    identity = base.jobs(flow)[0].decode()
    flow.sent.clear()
    return source_id, identity


def state(flow, identity):
    page = flow.client.get('/admin/startup-sources')
    assert page.status_code == 200
    return BeautifulSoup(page.data, 'html.parser').select_one(f'[data-analysis-id="{identity}"]').select('td')[2].text


def edit_source(flow, source_id, **values):
    form = {'name': 'Synthetic directory', 'url': base.URL, 'source_type': 'startup', 'is_active': 'on'}
    form.update(values)
    form['csrf_token'] = flow.csrf(f'/admin/startup-sources/{source_id}/edit')
    assert flow.client.post(f'/admin/startup-sources/{source_id}/edit', data=form).status_code == 302


@pytest.mark.parametrize('when', ['before', 'provider'])
@pytest.mark.parametrize('change', ['disable', 'delete', 'url-aba', 'type-aba'])
def test_source_authority_changes_never_apply_or_repay(discovery, monkeypatch, when, change):
    source_id, identity = prepared(discovery)

    def alter():
        if change == 'delete':
            assert discovery.client.post(f'/admin/startup-sources/{source_id}/delete', data={
                'csrf_token': discovery.csrf('/admin/startup-sources')}).status_code == 302
        elif change == 'disable':
            edit_source(discovery, source_id, is_active='')
        else:
            edit_source(discovery, source_id, **({'url': 'https://elsewhere.example.test'}
                                                if change == 'url-aba' else {'source_type': 'research_lab'}))
            edit_source(discovery, source_id)

    def provider(**kwargs):
        alter()  # Real HTTP write while the SDK boundary is active: no business lock held.
        return discovery.complete(**kwargs)

    if when == 'before':
        alter()
    else:
        monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    analyze.run(identity)
    analyze.run(identity)
    assert state(discovery, identity) == 'stale'
    assert len(discovery.calls) == (when == 'provider')
    db.session.remove()
    company = db.session.query(Company).one()
    assert company.ai_analysis is None
    assert db.session.query(LLMReservation).count() == (when == 'provider')
    assert discovery.client.get('/api/v1/news').json['total'] == 0


def test_manual_analysis_during_provider_call_is_not_overwritten(discovery, monkeypatch):
    _, identity = prepared(discovery)

    def provider(**kwargs):
        path = '/companies/alpine-synthetic/edit-analysis'
        assert discovery.client.post(path, data={
            'csrf_token': discovery.csrf(path), 'overview': 'Manual truth', 'recommendation': '持续监控',
        }).status_code == 302
        return discovery.complete(**kwargs)

    monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    analyze.run(identity)
    assert state(discovery, identity) == 'stale'
    db.session.remove()
    assert db.session.query(Company).one().ai_analysis['overview'] == 'Manual truth'
    assert len(discovery.calls) == 1


def test_duplicate_delivery_during_paid_call_and_after_restart_never_pays_twice(discovery, monkeypatch):
    _, identity = prepared(discovery)

    def provider(**kwargs):
        analyze.run(identity)
        recover.run()
        return discovery.complete(**kwargs)

    monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    analyze.run(identity)
    analyze.run(identity)
    recover.run()
    assert state(discovery, identity) == 'succeeded'
    assert len(discovery.calls) == 1 and not discovery.sent


def test_concurrent_consumers_have_one_owner(discovery, app):
    _, identity = prepared(discovery)
    barrier = Barrier(2)

    def deliver():
        with app.app_context():
            barrier.wait(timeout=5)
            analyze.run(identity)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: deliver(), range(2)))
    assert state(discovery, identity) == 'succeeded'
    assert len(discovery.calls) == 1


def test_broker_loss_keeps_company_and_intent_for_bounded_recovery(discovery, monkeypatch):
    from celery import Celery
    base.add_source(discovery)

    def broken(*args, **kwargs):
        raise RuntimeError('PRIVATE_BROKER_PAYLOAD')

    original = Celery.send_task
    monkeypatch.setattr(Celery, 'send_task', broken)
    # The scan itself has already been delivered; fail only its LLM dispatch.
    from app.crawlers.startup_discovery import scan_startup_sources
    scan_startup_sources.run()
    db.session.remove()
    identity = base.jobs(discovery)[0].decode()
    assert state(discovery, identity) == 'queued'
    recover.run()
    assert not discovery.calls
    clock = time.time()
    monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 121)
    monkeypatch.setattr(Celery, 'send_task', original)
    recover.run()
    assert discovery.sent == [(analyze.name, [identity], {'queue': 'llm'})]
    analyze.run(identity)
    assert state(discovery, identity) == 'succeeded'
    assert len(discovery.calls) == 1


@pytest.mark.parametrize('fault', ['unknown', 'no-ceiling', 'budget', 'settlement'])
def test_paid_or_unpaid_failure_is_terminal_without_scan_reset(discovery, monkeypatch, app, fault, caplog):
    _, identity = prepared(discovery)
    if fault == 'no-ceiling':
        db.session.query(LLMConfig).one().billing_input_limit = None
        db.session.commit()
    elif fault == 'budget':
        app.config['LLM_DAILY_BUDGET_USD'] = '0.000001'
    elif fault == 'settlement':
        with db.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TRIGGER fail_usage BEFORE INSERT ON llm_usage_log BEGIN SELECT RAISE(FAIL, 'PRIVATE_USAGE_SQL'); END")
    else:
        def unknown(**kwargs):
            discovery.calls.append(kwargs)
            raise TimeoutError('PRIVATE_UNKNOWN_USAGE')
        monkeypatch.setattr(discovery.provider.litellm, 'completion', unknown)
    analyze.run(identity)
    assert state(discovery, identity) == 'blocked'
    analyze.run(identity)
    recover.run()
    base.scan(discovery)
    assert len(base.jobs(discovery)) == 1
    expected = int(fault in ('unknown', 'settlement'))
    assert len(discovery.calls) == expected
    db.session.remove()
    company = db.session.query(Company).one()
    assert company.ai_analysis is None and company.ai_analysis_failures == 1
    rows = db.session.query(LLMReservation).all()
    assert len(rows) == expected
    if rows:
        assert rows[0].state == ('unknown' if fault == 'unknown' else 'reserved')
        assert rows[0].reserved_usd > 0
    assert 'PRIVATE_' not in caplog.text + discovery.client.get('/admin/startup-sources').text


@pytest.mark.parametrize('boundary', ['job-insert', 'producer-commit', 'claim-commit', 'result-write', 'result-commit'])
def test_storage_failure_and_commit_ack_loss_never_duplicate_paid_work(discovery, boundary, caplog):
    source_id = base.add_source(discovery)
    if boundary == 'job-insert':
        with db.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TRIGGER fail_job BEFORE INSERT ON startup_analysis_job BEGIN SELECT RAISE(FAIL, 'PRIVATE_JOB_SQL'); END")
        base.scan(discovery)
        assert not base.jobs(discovery)
        assert db.session.query(Company).count() == 0
        assert db.session.get(StartupSource, source_id).last_scanned_at is None
        assert not discovery.sent and not discovery.calls
        return
    if boundary != 'producer-commit':
        base.scan(discovery)
        identity = base.jobs(discovery)[0].decode()
        discovery.sent.clear()
    if boundary == 'result-write':
        with db.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TRIGGER fail_result BEFORE UPDATE OF ai_analysis ON company BEGIN SELECT RAISE(FAIL, 'PRIVATE_RESULT_SQL'); END")
        analyze.run(identity)
    else:
        failed = []

        def mark_commit(session):
            # New intents may leave the ORM weak identity map after flush.
            # Identify creation BEFORE commit, not a later queued dispatch commit.
            rows = session.new if boundary == 'producer-commit' else session.identity_map.values()
            wanted = {'producer-commit': 'queued', 'claim-commit': 'running', 'result-commit': 'succeeded'}[boundary]
            session.info['target_commit'] = any(isinstance(r, StartupAnalysisJob) and r.state == wanted for r in rows)

        def lose_ack(session):
            if not failed and session.info.get('target_commit'):
                failed.append(True)
                raise OperationalError(None, None, RuntimeError('PRIVATE_COMMIT_ACK'))

        event.listen(Session, 'before_commit', mark_commit)
        event.listen(Session, 'after_commit', lose_ack)
        try:
            if boundary == 'producer-commit':
                base.scan(discovery)
            else:
                analyze.run(identity)
        finally:
            event.remove(Session, 'before_commit', mark_commit)
            event.remove(Session, 'after_commit', lose_ack)
        assert failed, 'Fault must actually reach the intended commit'
        if boundary == 'producer-commit':
            identity = base.jobs(discovery)[0].decode()
            recover.run()
            assert discovery.sent == [(analyze.name, [identity], {'queue': 'llm'})]
            analyze.run(identity)
    analyze.run(identity)
    assert len(discovery.calls) == (0 if boundary == 'claim-commit' else 1)
    expected = 'blocked' if boundary in ('claim-commit', 'result-write') else 'succeeded'
    assert state(discovery, identity) == expected
    assert 'PRIVATE_' not in caplog.text + discovery.client.get('/admin/startup-sources').text


@pytest.mark.parametrize('expired', ['queued', 'running'])
def test_expiry_retains_uncertain_execution_without_repayment(discovery, monkeypatch, expired):
    _, identity = prepared(discovery)
    clock = time.time()
    if expired == 'queued':
        monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 86401)
    else:
        def killed(**kwargs):
            discovery.calls.append(kwargs)
            raise SystemExit('Synthetic worker disappearance')
        monkeypatch.setattr(discovery.provider.litellm, 'completion', killed)
        with pytest.raises(SystemExit):
            analyze.run(identity)
        monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 181)
    recover.run()
    analyze.run(identity)
    assert state(discovery, identity) == 'blocked'
    assert len(discovery.calls) == int(expired == 'running')
    db.session.remove()
    if expired == 'running':
        assert db.session.query(LLMReservation).one().state == 'reserved'


def test_late_provider_success_is_charged_but_not_applied(discovery, monkeypatch):
    _, identity = prepared(discovery)
    clock = time.time()

    def late(**kwargs):
        monkeypatch.setattr('app.llm.budget.time.time', lambda: clock + 181)
        return discovery.complete(**kwargs)

    monkeypatch.setattr(discovery.provider.litellm, 'completion', late)
    analyze.run(identity)
    assert state(discovery, identity) == 'blocked'
    db.session.remove()
    assert db.session.query(Company).one().ai_analysis is None
    assert db.session.query(LLMReservation).one().state == 'settled'


@pytest.mark.parametrize('identity', ['', 'unknown-job', 0, False, []])
def test_public_client_rejects_missing_identity_even_with_valid_cache(discovery, monkeypatch, identity):
    from app.llm.client import LLMClient
    from app.llm.budget import BudgetError
    from tests.test_llm.conftest import MemoryRedis
    cache = MemoryRedis()
    monkeypatch.setattr(discovery.provider, 'redis_client', cache)
    LLMClient().analyze_company(name='Cached company')
    with pytest.raises(BudgetError):
        LLMClient().analyze_company(name='Cached company', discovery_job=identity)
    assert len(discovery.calls) == 1


def test_pricing_changed_after_route_snapshot_cannot_use_stale_quote(discovery, monkeypatch):
    from tests.test_llm.conftest import MemoryRedis
    _, identity = prepared(discovery)
    cache = MemoryRedis()

    def get(key):
        if key.startswith('llm_cache:'):
            db.session.query(LLMConfig).one().cost_per_1k_input = '1'
            db.session.commit()
        return None

    cache.get = get
    monkeypatch.setattr(discovery.provider, 'redis_client', cache)
    analyze.run(identity)
    assert state(discovery, identity) == 'blocked'
    assert not discovery.calls
    assert db.session.query(LLMReservation).count() == 0


def test_reverted_queued_state_with_prior_execution_never_reopens(discovery):
    _, identity = prepared(discovery)
    analyze.run(identity)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE startup_analysis_job SET state='queued' WHERE id=:id"), {'id': identity})
    analyze.run(identity)
    assert len(discovery.calls) == 1
    assert state(discovery, identity) in ('blocked', 'stale')
