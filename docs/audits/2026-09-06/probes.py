"""Offline audit probes of current defects, NOT the project's regression suite.
Run from repository root using an isolated Python 3.12 environment.
Only SQLite in-memory data and mocks; no external requests/LLM/SMTP.
"""
import ast
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path.cwd()
RUN_DIR = Path(tempfile.mkdtemp(prefix='fsource-audit-probes-'))
sys.path.insert(0, str(ROOT))
os.environ.update({
    'FLASK_ENV': 'testing', 'DATABASE_URL': 'sqlite:///:memory:',
    'REDIS_URL': 'redis://127.0.0.1:1/0',
    'CELERY_BROKER_URL': 'memory://', 'SENTRY_DSN': '',
    'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'DO_NOT_TRACK': '1',
    'LOG_FILE': str(RUN_DIR / 'app.log'),
})

def deny_network(*args, **kwargs):
    raise RuntimeError('AUDIT: network disabled')

socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network
socket.getaddrinfo = deny_network

from app import create_app
from app.extensions import db
from app.models import Article, ArticleCategory, Category, Company, CrawlLog, LLMConfig, NewsSource, User
from app.models.setting import SystemSetting
from app.crawlers.base import BaseCrawler, RawArticle
from app.crawlers.html_crawler import HTMLCrawler
from app.llm.client import LLMClient
from app.llm.tasks import _link_categories, _save_revision
from app.llm.circuit_breaker import CircuitBreaker
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from jinja2 import TemplateNotFound

app = create_app('testing')
app.config.update(SECRET_KEY='isolated-audit-only', WTF_CSRF_ENABLED=True)
results = []

def record(name, fn):
    with app.app_context():
        db.create_all()
        try:
            evidence = fn()
            results.append({'probe': name, 'status': 'reproduced', 'evidence': evidence})
        except Exception as exc:
            results.append({'probe': name, 'status': 'unexpected', 'error': type(exc).__name__ + ': ' + str(exc)[:300]})
        finally:
            db.session.rollback()
            db.session.remove()
            db.drop_all()

def source():
    obj = NewsSource(name='Audit', slug='audit', url='https://news.invalid/section/', category='national', feed_type='html_scrape')
    db.session.add(obj)
    db.session.commit()
    return obj

def csrf(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)

def password_reset():
    user = User(email='admin@audit.invalid', is_admin=True, password_hash=generate_password_hash('old-local-only'))
    db.session.add(user)
    db.session.commit()
    with app.test_client() as client:
        token = csrf(client, '/subscribe/settings?email=admin@audit.invalid')
        response = client.post('/subscribe/settings', data={'email':user.email,'password':'new-local-only','csrf_token':token})
        db.session.refresh(user)
        assert response.status_code == 302 and check_password_hash(user.password_hash, 'new-local-only')
        token = csrf(client, '/auth/login')
        response = client.post('/auth/login', data={'email':user.email,'password':'new-local-only','csrf_token':token})
        assert response.status_code == 302 and client.get('/admin/').status_code == 200
    return 'Anonymous CSRF-valid request changed isolated admin password; new password permits /admin/ (200).'

def markdown_xss():
    src = source()
    marker = '<img src=x onerror="window.auditMarker=1">'
    article = Article(source_id=src.id, external_id='one', url='https://news.invalid/one', title_fr='Audit', insight_zh=marker)
    db.session.add(article)
    db.session.commit()
    response = app.test_client().get(f'/news/{article.id}')
    assert response.status_code == 200 and marker in response.text
    assert marker not in str(app.jinja_env.filters['paragraphs'](marker))
    return 'Article detail emits raw img/onerror from insight; paragraphs comparison escapes it. No browser script executed.'

def email_templates():
    missing = []
    for template in ['email/daily_digest.html', 'email/keyword_alert.html']:
        try:
            app.jinja_env.get_template(template)
        except TemplateNotFound:
            missing.append(template)
    assert len(missing) == 2
    app.jinja_env.get_template('daily_digest.html')
    return {'missing': missing, 'actual_loadable': 'daily_digest.html'}

def digest_context():
    from app.email.sender import send_digest_email
    user = User(email='reader@audit.invalid')
    db.session.add(user)
    db.session.commit()
    with patch('app.email.sender.render_template', return_value='offline') as render, patch('app.email.sender.mail.send'):
        send_digest_email(user, {'date':'2026-09-06','articles':[],'top_insights':[{'id':1}], 'article_count':1})
        assert 'top_insights' not in render.call_args.kwargs
    return 'Sender does not pass top_insights, even if template path is patched; SMTP was mocked.'

def url_resolution():
    crawler = HTMLCrawler(source())
    actual = crawler._resolve_url('/story/1')
    assert actual == 'https://news.invalid/section/story/1'
    return {'actual': actual, 'expected': 'https://news.invalid/story/1'}

class EmptyCrawler(BaseCrawler):
    def fetch_articles(self): return []

class FailedCrawler(BaseCrawler):
    def fetch_articles(self): raise RuntimeError('fixture fetch failure')

def empty_success():
    result = EmptyCrawler(source()).run()
    log = CrawlLog.query.one()
    assert result.articles_found == 0 and log.status == 'success'
    return '0 fetched / 0 new, crawl_log.status=success, no quality evidence.'

def swallowed_retry():
    from app.crawlers.tasks import crawl_source
    src = source()
    with patch('app.crawlers.tasks.get_crawler', return_value=FailedCrawler(src)), patch.object(crawl_source, 'retry') as retry:
        result = crawl_source.run(src.id)
        assert result['errors'] == ['fixture fetch failure'] and not retry.called
    return 'crawl_source returned errors as a successful task result; retry() not called.'

def batch_duplicate():
    src = source()
    raw = RawArticle('Audit', 'https://news.invalid/one', 'same-id')
    class DuplicateCrawler(BaseCrawler):
        def fetch_articles(self): return [raw, raw]
    assert len(DuplicateCrawler(src).dedup([raw, raw])) == 2
    try:
        DuplicateCrawler(src).run()
    except PendingRollbackError:
        db.session.rollback()
        assert Article.query.count() == 0 and CrawlLog.query.one().status == 'running'
        return 'Batch duplicates pass dedup; save fails, error handler raises PendingRollbackError; log remains running.'
    raise AssertionError('Expected PendingRollbackError')

def llm_transaction():
    src = source()
    article = Article(source_id=src.id,external_id='one',url='https://news.invalid/one',title_fr='Audit')
    category = Category(name='AI',slug='ai')
    config = LLMConfig(provider='audit', model='mock', tasks=['insight'])
    db.session.add_all([article,category,config]); db.session.commit()
    client = LLMClient()
    article.title_zh = 'Pending business field'
    _link_categories(article,[{'category':'ai','confidence':0.9}])
    fake = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='offline'))],usage=None)
    with patch('app.llm.client.litellm.completion',return_value=fake), patch.object(client._breaker,'record_success'):
        client._call_llm(config, [], 'insight', article.id)
    db.session.rollback()
    db.session.refresh(article)
    assert article.title_zh == 'Pending business field' and ArticleCategory.query.count() == 1
    _link_categories(article,[{'category':'ai','confidence':0.9}])
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return 'LLM usage commit persisted pending article+category; rollback cannot undo; category retry raises IntegrityError.'
    raise AssertionError('Expected duplicate category failure')

def stale_company_cache():
    client = LLMClient()
    with patch.object(client, '_call_with_cache', return_value={}) as call:
        client.analyze_company('Example',sector='AI',recent_news='Old news',website_excerpt='Old body')
        first = call.call_args.args[2]
        client.analyze_company('Example',sector='AI',recent_news='New funding',website_excerpt='New body')
        second = call.call_args.args[2]
    assert first == second
    return 'Changing news and non-empty website content produces identical company analysis cache key.'

def routing():
    tree = ast.parse((ROOT/'scripts/seed_llm_configs.py').read_text())
    configs = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CONFIGS' for t in n.targets))
    db.session.add_all([LLMConfig(**data) for data in configs]); db.session.commit()
    client = LLMClient()
    with patch.object(client._breaker,'is_open',return_value=False):
        output={task:client._get_config(task).provider+'/'+client._get_config(task).model for task in ['ner','classify','insight']}
    assert output['ner'].endswith('nano') and output['insight'].startswith('deepseek/')
    return output

def bad_json_cache():
    client = LLMClient()
    with patch.object(client,'_get_cached',return_value=None), patch.object(client,'_check_daily_budget'), patch.object(client,'_get_config',return_value=object()), patch.object(client,'_call_llm',return_value='not-json'), patch.object(client,'_set_cache') as cache:
        result = client._call_with_cache('ner',[],'offline',parse_json=True)
        assert result == [] and cache.call_args.args == ('offline','[]')
    return 'Malformed NER response becomes [] and is cached as a successful empty extraction.'

def redis_error():
    import redis
    fake = SimpleNamespace(get=lambda *args: (_ for _ in ()).throw(redis.ConnectionError('offline fixture')))
    with patch('app.llm.circuit_breaker.redis_client',fake):
        try: CircuitBreaker().is_open('test')
        except redis.ConnectionError: return 'Redis connection error propagates; advertised in-memory fallback not used.'
    raise AssertionError('Expected Redis error')

def ssrf_guard():
    from app.utils.website_fetcher import fetch_website_excerpt
    fake = SimpleNamespace(ok=True,text='<p>'+'offline useful content '*20+'</p>')
    with patch('app.utils.website_fetcher.requests.get',return_value=fake) as get:
        excerpt,status = fetch_website_excerpt('http://127.0.0.1/private')
        assert status == 'ok' and get.called
    return 'Private URL reaches mocked transport; no host/IP validation. No actual connection made.'

def date_to():
    from app.web.views.news import _build_article_query
    src = source()
    db.session.add(Article(source_id=src.id,external_id='one',url='https://news.invalid/one',title_fr='Audit',published_at=datetime(2026,9,6,12)))
    db.session.commit()
    with app.test_request_context('/?date_to=2026-09-06'):
        assert _build_article_query().count() == 0
    return 'date_to=2026-09-06 excludes a noon article on that date.'

def revision_tracking():
    company = Company(name='Example',slug='example',ai_analysis={'overview':'old'},ai_revision_history=[{'timestamp':'before'}])
    db.session.add(company); db.session.commit()
    _save_revision(company, {'overview':'new'})
    company.ai_analysis = {'overview':'new'}
    db.session.commit(); db.session.expire_all()
    assert len(company.ai_revision_history) == 1
    return 'Appending revision in place then slicing lost new entry after commit/reload (history already non-empty).'

def schedule_config():
    from celery_app import celery
    from app.crawlers.tasks import crawl_all_sources
    SystemSetting.set('crawl_daily_hour','14'); db.session.commit()
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026,9,6,1,tzinfo=tz)
    with patch('app.crawlers.tasks.datetime', Clock):
        result=crawl_all_sources.run()
    assert celery.conf.beat_schedule['daily-crawl-all']['schedule'].hour == {1} and result['skipped']
    return 'Beat remains fixed at 01:00; a configured 14:00 causes scheduled task to skip rather than reschedule.'

def json_logging():
    formatter=logging.Formatter('{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}')
    record=logging.LogRecord('audit',logging.INFO,'audit',1,'message with "quotes"\nand newline',(),None)
    try: json.loads(formatter.format(record))
    except json.JSONDecodeError: return 'LOG_FORMAT=json formatter does not JSON-escape quotes/newlines.'
    raise AssertionError('Expected invalid JSON')

for name,fn in [
    ('anonymous_admin_password_reset',password_reset), ('stored_xss_output',markdown_xss),
    ('email_template_paths',email_templates), ('digest_missing_highlights',digest_context),
    ('html_url_resolution',url_resolution), ('empty_crawl_success',empty_success),
    ('crawl_retry_swallowed',swallowed_retry), ('batch_duplicates_and_rollback',batch_duplicate),
    ('llm_commit_and_category_retry',llm_transaction), ('company_cache_collision',stale_company_cache),
    ('seed_routing_mismatch',routing), ('malformed_json_cached',bad_json_cache),
    ('redis_failure_not_degraded',redis_error), ('private_url_no_guard',ssrf_guard),
    ('end_date_excludes_day',date_to), ('revision_json_lost',revision_tracking),
    ('daily_schedule_setting',schedule_config), ('json_logging_not_json',json_logging),
]: record(name, fn)

output=RUN_DIR / 'probe-results.json'
output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
sys.exit(any(item['status']=='unexpected' for item in results))
