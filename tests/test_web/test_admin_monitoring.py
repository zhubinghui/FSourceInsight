"""One admin page answers "is the platform healthy, and if not, where?"."""
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from app import monitoring
from app.models.llm import LLMConfig, LLMUsageLog
from app.models.source import CrawlLog, NewsSource

LONG_ERROR = 'HTTPSConnectionPool(host=news.test.invalid): ' + 'certificate verify failed ' * 8 + 'END-OF-ERROR'


def _seed(db):
    now = datetime.utcnow()
    fresh = NewsSource(name='Fresh Feed', slug='fresh', url='https://fresh.test.invalid/', feed_type='rss',
                       category='national', last_crawled_at=now - timedelta(hours=1))
    stale = NewsSource(name='Stale Feed', slug='stale', url='https://stale.test.invalid/', feed_type='rss',
                       category='national', last_crawled_at=now - timedelta(days=3))
    paused = NewsSource(name='Paused Feed', slug='paused', url='https://paused.test.invalid/', feed_type='rss',
                        category='national', is_active=False)
    db.session.add_all([fresh, stale, paused])
    db.session.flush()
    db.session.add_all([
        CrawlLog(source_id=fresh.id, status='success', articles_new=3, finished_at=now),
        CrawlLog(source_id=stale.id, status='failed', error_message=LONG_ERROR, finished_at=now),
    ])
    config = LLMConfig(provider='openai', model='synthetic')
    db.session.add(config)
    db.session.flush()
    db.session.add_all([LLMUsageLog(config_id=config.id, task_type='translate', success=True, cost_usd=0.5),
                        LLMUsageLog(config_id=config.id, task_type='translate', success=True, cost_usd=0.25),
                        LLMUsageLog(config_id=config.id, task_type='ner', success=False, cost_usd=0)])
    db.session.commit()


def _page(client):
    response = client.get('/admin/monitoring')
    assert response.status_code == 200
    return BeautifulSoup(response.text, 'html.parser')


def test_monitoring_shows_stale_sources_full_errors_llm_and_budget(app, db, client, login):
    app.config['LLM_DAILY_BUDGET_USD'] = 5.0
    _seed(db)
    login('admin')

    page = _page(client)
    text = page.get_text(' ', strip=True)

    stale = [row.get_text(' ', strip=True) for row in page.select('#stale-sources tbody tr')]
    assert len(stale) == 1 and 'Stale Feed' in stale[0]
    assert 'END-OF-ERROR' in page.select_one('#failed-crawls').get_text()
    assert page.select_one('[data-metric=llm-failure-rate]').get_text(strip=True) == '33.3%'
    assert page.select_one('[data-metric=llm-cost-today]').get_text(' ', strip=True) == '$0.75 of $5.00'
    assert page.select_one('[data-metric=failed-crawls-24h]').get_text(strip=True) == '1'
    assert 'Queue depth unavailable' in text
    assert [a.get_text(' ', strip=True) for a in page.select('aside .sidebar-nav a.active')] == ['System Health']


def test_queue_depths_are_listed_when_the_broker_answers(db, client, login, monkeypatch):
    class Broker:
        def llen(self, queue):
            return {'crawl': 2, 'llm': 41, 'email': 0, 'crawl_learn': 0}[queue]
    monkeypatch.setattr(monitoring, '_broker', lambda: Broker())
    login('admin')

    page = _page(client)

    depths = {cell['data-queue']: cell.get_text(strip=True) for cell in page.select('[data-queue]')}
    assert depths == {'crawl': '2', 'llm': '41', 'email': '0', 'crawl_learn': '0'}


def test_public_health_detail_keeps_its_shape(db, client):
    _seed(db)

    body = client.get('/health/detail').get_json()

    assert body['crawl'] == {'active_sources': 2, 'crawls_24h': 2, 'failed_24h': 1, 'stale_sources': 1}
    assert body['llm'] == {'calls_24h': 3, 'failures_24h': 1, 'failure_rate': '33.3%'}
    assert set(body['pipeline']) == {'articles_24h', 'unprocessed_queue'}


def test_monitoring_requires_an_administrator(db, client, login):
    login('owner')
    assert client.get('/admin/monitoring').status_code == 302
