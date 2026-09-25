"""Durable article LLM jobs: Admin requests, claimed consumption and recovery (spec §6)."""
from datetime import timedelta

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import update

from app.llm import article_jobs
from app.llm.article_tasks import process, recover
from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob
from tests.test_llm.test_pipeline import article_reply

TASK = 'app.llm.article_tasks.process'


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, kwargs=None, **options:
                        messages.append((name, args, options.get('queue'))))
    return messages


def latest(db, article_id):
    db.session.remove()
    return article_jobs.latest(article_id)


def test_admin_reprocess_queues_one_forced_job_and_absorbs_a_repeat(db, llm_env, client, login, csrf_token, sent):
    login('admin')
    path = f'/admin/articles/{llm_env.article.id}'
    for _ in range(2):
        assert client.post(f'{path}/reprocess', data={'csrf_token': csrf_token()}).status_code == 302
    item = latest(db, llm_env.article.id)
    assert (item.state, item.trigger, item.force) == ('queued', 'manual', True)
    assert sent == [(TASK, [item.id], 'llm')]
    page = BeautifulSoup(client.get(path).text, 'html.parser')
    assert page.select_one('[data-llm-job-state]').get_text(strip=True) == 'queued'
    assert llm_env.provider.calls == []


def test_duplicate_delivery_pays_once(db, llm_env, sent):
    llm_env.provider.reply = article_reply
    identity, created = article_jobs.request(llm_env.article.id, 'manual')
    assert created
    process.run(identity)
    calls = len(llm_env.provider.calls)
    process.run(identity)
    assert calls > 0 and len(llm_env.provider.calls) == calls
    item = latest(db, llm_env.article.id)
    assert (item.state, item.reason, item.active_article_id) == ('done', 'applied', None)
    assert db.session.get(Article, llm_env.article.id).llm_processed


def test_failure_is_recorded_without_automatic_paid_retry(db, llm_env, client, login, csrf_token, sent):
    login('admin')  # before latest() removes the session that holds the user fixtures
    article_id = llm_env.article.id
    llm_env.provider.error = RuntimeError('provider down')
    identity, _ = article_jobs.request(article_id, 'manual')
    process.run(identity)
    failed = latest(db, article_id)
    assert (failed.state, failed.reason) == ('failed', 'execution_error')
    calls = len(llm_env.provider.calls)
    recover.run()
    assert len(llm_env.provider.calls) == calls
    assert client.post('/admin/llm-reprocess', data={'csrf_token': csrf_token(), 'limit': '50'}).status_code == 302
    again = latest(db, article_id)
    assert again.id != identity and (again.state, again.trigger) == ('queued', 'manual')


def test_recovery_respects_spacing_and_expiry(db, llm_env, sent, monkeypatch):
    base = article_jobs.now()
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    article_jobs.publish(identity)
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(seconds=60))
    recover.run()
    assert len(sent) == 1
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(seconds=130))
    recover.run()
    assert sent == [(TASK, [identity], 'llm')] * 2
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(hours=25))
    recover.run()
    item = latest(db, llm_env.article.id)
    assert (item.state, item.reason) == ('expired', 'queue_expired')


def test_interrupted_running_job_is_closed_and_a_late_finish_is_ignored(db, llm_env, sent, monkeypatch):
    base = article_jobs.now()
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    assert article_jobs.claim(identity, 'worker-1').article_id == llm_env.article.id
    assert article_jobs.claim(identity, 'worker-2') is None
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(minutes=31))
    recover.run()
    article_jobs.finish(identity, 'worker-1', 'done', 'applied')
    item = latest(db, llm_env.article.id)
    assert (item.state, item.reason) == ('failed', 'interrupted')
    assert sent == []


def test_old_direct_messages_only_create_a_job(db, llm_env, sent):
    from app.llm.tasks import process_article_llm
    process_article_llm.run(llm_env.article.id, force=True)
    assert llm_env.provider.calls == []
    item = latest(db, llm_env.article.id)
    assert (item.trigger, item.force, item.state) == ('legacy_message', True, 'queued')
    assert sent == [(TASK, [item.id], 'llm')]


def test_job_for_a_deleted_article_closes_without_paying(db, llm_env, sent):
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    # SQLite does not enforce FKs here; emulate MySQL's ON DELETE SET NULL.
    db.session.execute(update(ArticleLLMJob).where(ArticleLLMJob.id == identity).values(article_id=None))
    db.session.commit()
    process.run(identity)
    db.session.remove()
    item = db.session.get(ArticleLLMJob, identity)
    assert (item.state, item.reason, item.active_article_id) == ('failed', 'article_unavailable', None)
    assert llm_env.provider.calls == []


def test_monitoring_and_backfill_report_job_states(db, llm_env, client, login, sent):
    assert article_jobs.backfill() == 1
    assert ArticleLLMJob.query.count() == 0
    assert article_jobs.backfill(apply=True) == 1
    assert article_jobs.backfill(apply=True) == 0
    login('admin')
    page = BeautifulSoup(client.get('/admin/monitoring').text, 'html.parser')
    assert page.select_one('[data-llm-jobs="queued"]').get_text(strip=True) == '1'
