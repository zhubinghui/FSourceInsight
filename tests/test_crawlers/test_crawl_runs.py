"""Claims, fencing, schedule settlement and the legacy final commit through public entry points."""
from datetime import datetime, timedelta

import pytest
import requests

from app.crawlers import runs, schedule
from app.crawlers.base import BaseCrawler, RawArticle
from app.crawlers.fetcher import FetchError
from app.llm import article_jobs
from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob, CrawlSourceState
from app.models.source import CrawlLog, NewsSource
from tests.support.runs import Clock, claimed

ITEM = RawArticle(title='Research', url='https://test.invalid/news', external_id='guid-1')
PROCESS = 'app.llm.article_tasks.process'


@pytest.fixture
def clock(monkeypatch):
    value = Clock(datetime(2026, 9, 25, 10, 0))
    monkeypatch.setattr(schedule, 'now', value)
    return value


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, kwargs=None, **options:
                        messages.append((name, args, options.get('queue'))))
    return messages


@pytest.fixture
def source(db):
    item = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid/',
                      feed_url='https://test.invalid/feed', category='national', crawl_frequency_minutes=360)
    db.session.add(item)
    db.session.commit()
    return item.id


class FixtureCrawler(BaseCrawler):
    def __init__(self, source, articles=(), error=None, during_fetch=None):
        super().__init__(source)
        self.articles, self.error, self.during_fetch = list(articles), error, during_fetch

    def fetch_articles(self):
        if self.during_fetch:
            self.during_fetch()
        if self.error:
            raise self.error
        return self.articles


def crawl(db, source_id, **kwargs):
    return FixtureCrawler(db.session.get(NewsSource, source_id), **kwargs).run(claimed(source_id))


def fresh(db, model, key):
    db.session.remove()
    return db.session.get(model, key)


def test_dispatcher_claims_each_due_source_once_and_sends_only_ids(db, source, clock, sent):
    from app.crawlers.tasks import dispatch_due_crawls
    assert dispatch_due_crawls.run() == {'dispatched': 1}
    assert dispatch_due_crawls.run() == {'dispatched': 0}
    state = fresh(db, CrawlSourceState, source)
    assert sent == [('app.crawlers.tasks.crawl_source', [source, state.claim_id], 'crawl')]
    assert state.fence == 1 and state.lease_expires_at == clock() + timedelta(minutes=15)
    assert db.session.get(CrawlLog, state.running_log_id).status == 'running'


def test_legacy_run_commits_articles_jobs_log_and_schedule_together(db, source, clock, sent):
    claim = claimed(source)
    result = FixtureCrawler(db.session.get(NewsSource, source), [ITEM, ITEM]).run(claim)
    assert (result.status, result.articles_new) == ('success', 1)
    db.session.remove()
    article, job = Article.query.one(), ArticleLLMJob.query.one()
    assert (job.article_id, job.state, job.trigger, job.crawl_log_id) == (article.id, 'queued', 'crawl', claim.log_id)
    assert sent == [(PROCESS, [job.id], 'llm')]
    log = db.session.get(CrawlLog, claim.log_id)
    assert (log.status, log.outcome, log.route, log.articles_new) == ('success', 'success', 'legacy', 1)
    state = db.session.get(CrawlSourceState, source)
    assert (state.claim_id, state.lease_expires_at, state.running_log_id) == (None, None, None)
    assert (state.next_due_at, state.due_reason) == (clock() + timedelta(minutes=360), 'schedule')
    assert db.session.get(NewsSource, source).last_crawled_at == clock()


def test_expired_claim_cannot_commit_after_another_worker_reclaims(db, source, clock, sent):
    first = claimed(source)

    def reclaimed_meanwhile():
        clock.advance(minutes=16)
        assert runs.claim(source, due_only=False) is not None

    result = FixtureCrawler(db.session.get(NewsSource, source), [ITEM], during_fetch=reclaimed_meanwhile).run(first)
    assert result.status == 'stale'
    assert Article.query.count() == 0 and ArticleLLMJob.query.count() == 0
    assert fresh(db, CrawlLog, first.log_id).outcome == 'lease_expired'
    state = db.session.get(CrawlSourceState, source)
    assert state.fence == 2 and state.claim_id is not None


def test_expired_lease_alone_blocks_the_commit_and_frees_the_source(db, source, clock, sent):
    claim = claimed(source)
    result = FixtureCrawler(db.session.get(NewsSource, source), [ITEM],
                            during_fetch=lambda: clock.advance(minutes=16)).run(claim)
    assert result.status == 'stale' and Article.query.count() == 0
    assert fresh(db, CrawlLog, claim.log_id).outcome == 'stale'
    assert db.session.get(CrawlSourceState, source).claim_id is None


@pytest.mark.parametrize('error, code, outcome, wait', [
    (requests.Timeout('slow'), 'timeout', 'failed', timedelta(minutes=15)),
    (FetchError('robots_unavailable'), 'robots_unavailable', 'blocked', timedelta(hours=24)),
    (FetchError('rate_limited', 3600), 'rate_limited', 'failed', timedelta(hours=1)),
])
def test_failures_are_classified_into_the_schedule(db, source, clock, sent, error, code, outcome, wait):
    claim = claimed(source)
    result = FixtureCrawler(db.session.get(NewsSource, source), error=error).run(claim)
    assert result.status == 'failed'
    log = fresh(db, CrawlLog, claim.log_id)
    assert (log.status, log.outcome, log.error_code) == ('failed', outcome, code)
    state = db.session.get(CrawlSourceState, source)
    assert state.next_due_at == clock() + wait and state.consecutive_failures == 1
    assert state.attention_reason == (code if outcome == 'blocked' else None)


def test_three_empty_extractions_ask_for_attention_and_success_clears_it(db, source, clock, sent):
    for _ in range(3):
        crawl(db, source)
        clock.advance(hours=7)
    state = fresh(db, CrawlSourceState, source)
    assert (state.attention_reason, state.consecutive_failures) == ('extraction_failed', 3)
    assert CrawlLog.query.order_by(CrawlLog.id.desc()).first().error_code == 'empty_extraction'
    crawl(db, source, articles=[ITEM])
    state = fresh(db, CrawlSourceState, source)
    assert (state.attention_reason, state.consecutive_failures) == (None, 0)


def test_old_crawl_message_is_only_a_request_and_never_runs(db, source, clock, sent):
    from app.crawlers.tasks import crawl_source
    assert crawl_source.run(source) == {'requested': 'queued'}
    assert CrawlLog.query.count() == 0 and sent == []
    state = fresh(db, CrawlSourceState, source)
    assert (state.next_due_at, state.due_reason) == (clock(), 'manual')


def test_a_request_while_running_does_not_queue_a_second_crawl(db, source, clock, sent):
    claim = claimed(source)
    before = fresh(db, CrawlSourceState, source).next_due_at
    assert runs.request_now(source) == 'running'
    assert fresh(db, CrawlSourceState, source).next_due_at == before
    FixtureCrawler(db.session.get(NewsSource, source), [ITEM]).run(claim)
    assert fresh(db, CrawlSourceState, source).due_reason == 'schedule'


def test_crawl_task_ignores_a_claim_that_is_no_longer_current(db, source, clock, sent, monkeypatch):
    claim = claimed(source)
    FixtureCrawler(db.session.get(NewsSource, source), [ITEM]).run(claim)
    fetched = []
    monkeypatch.setattr('app.crawlers.registry.get_crawler', lambda item: fetched.append(item))
    from app.crawlers.tasks import crawl_source
    assert crawl_source.run(source, claim.claim_id) is None
    assert fetched == []


def test_run_no_longer_rescans_old_unprocessed_articles(db, source, clock, sent):
    db.session.add(Article(source_id=source, external_id='old', url='https://test.invalid/old', title_fr='Old'))
    db.session.commit()
    crawl(db, source, articles=[ITEM])
    job = ArticleLLMJob.query.one()
    assert sent == [(PROCESS, [job.id], 'llm')]
    assert db.session.get(Article, job.article_id).external_id == 'guid-1'


def test_broker_outage_after_commit_leaves_a_queued_job_for_recovery(db, source, clock, monkeypatch):
    def down(self, *args, **kwargs):
        raise ConnectionError('broker down')
    monkeypatch.setattr('celery.app.base.Celery.send_task', down)
    assert crawl(db, source, articles=[ITEM]).status == 'success'
    job = ArticleLLMJob.query.one()
    assert job.state == 'queued'
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, **options: messages.append((name, args)))
    later = article_jobs.now() + timedelta(seconds=130)
    monkeypatch.setattr(article_jobs, 'now', lambda: later)
    article_jobs.recover()
    assert messages == [(PROCESS, [job.id])]


def test_inactive_sources_are_never_claimed(db, source, clock, sent):
    item = db.session.get(NewsSource, source)
    item.is_active = False
    db.session.commit()
    from app.crawlers.tasks import dispatch_due_crawls
    assert dispatch_due_crawls.run() == {'dispatched': 0}
    assert runs.claim(source, due_only=False) is None
    assert runs.request_now(source) == 'inactive'
