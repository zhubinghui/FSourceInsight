"""Scheduled crawls follow the approved recipe; problems block instead of falling back (spec §4.5, §5.3)."""
import pytest

from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob, CrawlSourceState
from app.models.crawl_schema import CrawlSchemaVersion
from app.models.source import CrawlLog, NewsSource
from tests.support.runs import claimed
from tests.test_web import test_crawl_activation as activation
from tests.test_web import test_crawl_policy as policy
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_rollback as rollback

source = preview.source
fetch_network = preview.fetch_network


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, kwargs=None, **options: messages.append((name, args)))
    return messages


def scheduled_run(db, sent):
    from app.crawlers.tasks import crawl_source, dispatch_due_crawls
    assert dispatch_due_crawls.run() == {'dispatched': 1}
    (source_id, claim_id), = [args for name, args in sent if name == 'app.crawlers.tasks.crawl_source']
    sent.clear()
    crawl_source.run(source_id, claim_id)
    db.session.remove()
    return CrawlLog.query.order_by(CrawlLog.id.desc()).first()


def test_approved_schema_is_used_by_the_next_scheduled_crawl(db, client, source, csrf_token, fetch_network, sent):
    version = activation.approved(client, source, csrf_token, fetch_network)
    version_id = int(version.rsplit('/', 1)[1])
    log = scheduled_run(db, sent)
    assert (log.route, log.schema_version_id, log.outcome) == ('schema', version_id, 'success')
    article = Article.query.one()
    assert article.crawl_provenance['recipe'] == db.session.get(CrawlSchemaVersion, version_id).recipe_hash
    job = ArticleLLMJob.query.one()
    assert job.article_id == article.id and sent == [('app.llm.article_tasks.process', [job.id])]


def test_approval_makes_a_recently_crawled_source_due_immediately(db, client, source, csrf_token, fetch_network, sent):
    from app.crawlers.rss_crawler import RSSCrawler
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    RSSCrawler(db.session.get(NewsSource, source)).run(claimed(source))
    db.session.remove()
    assert db.session.get(CrawlSourceState, source).next_due_at > CrawlLog.query.one().finished_at
    activation.approved(client, source, csrf_token, fetch_network)
    log = scheduled_run(db, sent)
    # Identity compatibility may make this no_change; the point is that it ran at once on the schema route.
    assert log.route == 'schema' and log.outcome in ('no_change', 'success')


@pytest.mark.parametrize('change, code', [('revoke', 'policy_unavailable'), ('edit', 'schema_stale')])
def test_broken_schema_route_blocks_without_legacy_fallback(db, client, source, csrf_token, fetch_network, sent, change, code):
    activation.approved(client, source, csrf_token, fetch_network)
    if change == 'revoke':
        action, fields = policy.revoke_form(client, source)
        assert client.post(action, data=fields).status_code == 302
    else:
        preview.edit_source(client, source, csrf_token, url='https://news.test.invalid/moved')
    requests = len(fetch_network.events())
    log = scheduled_run(db, sent)
    assert (log.route, log.outcome, log.error_code) == ('schema', 'blocked', code)
    assert len(fetch_network.events()) == requests and Article.query.count() == 0
    assert db.session.get(CrawlSourceState, source).attention_reason == code


def test_a_run_claimed_before_approval_cannot_commit_after_it(db, client, source, csrf_token, fetch_network, sent):
    from app.crawlers.rss_crawler import RSSCrawler
    version, _ = activation.ready_report(client, source, csrf_token, fetch_network)
    claim = claimed(source)
    action, fields = activation.decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 302
    result = RSSCrawler(db.session.get(NewsSource, source)).run(claim)
    assert result.status == 'stale' and Article.query.count() == 0


def test_retired_schema_returns_the_source_to_the_legacy_crawler(db, client, source, csrf_token, fetch_network, sent):
    activation.approved(client, source, csrf_token, fetch_network)
    assert rollback.post(client, source, 'form[data-retire]').status_code == 302
    from app.crawlers import runs
    runs.request_now(source)
    log = scheduled_run(db, sent)
    assert (log.route, log.schema_version_id, log.outcome) == ('legacy', None, 'success')
    assert Article.query.one().crawl_provenance is None
