"""Destructive tests ONLY for a disposable MySQL container/database.

Run with unittest, not against the deployment database. The runner network must
be private, with its disposable server aliased as m0-mysql and no public ports.
"""
from contextlib import contextmanager
import os
import socket
import unittest
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Enum, String, create_engine, event, inspect, text
from sqlalchemy.engine import make_url

TEST_URL = os.environ.get('FSI_MYSQL_TEST_URL')
DATABASE = 'fsource_m0_validation'
HEAD = 'b6c2a4d9e710'
PREVIOUS = 'fd3132082a6b'


@unittest.skipUnless(TEST_URL, 'Requires explicitly provisioned disposable MySQL')
class MySQLM0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(TEST_URL)
        if (url.host != 'm0-mysql' or url.database != DATABASE
                or os.environ.get('FSI_DESTRUCTIVE_TESTS') != '1'):
            raise RuntimeError('Refusing destructive tests outside the disposable MySQL target')
        # Enforce the test network boundary even if a future test adds HTTP code.
        original_dns, original_connect = socket.getaddrinfo, socket.socket.connect
        addresses = {row[4][0] for row in original_dns('m0-mysql', 3306, type=socket.SOCK_STREAM)}

        def dns(host, port, *args, **kwargs):
            if host != 'm0-mysql' or port != 3306:
                raise AssertionError('Only disposable MySQL DNS is allowed')
            return original_dns(host, port, *args, **kwargs)

        def connect(sock, address):
            if not isinstance(address, tuple) or address[0] not in addresses or address[1] != 3306:
                raise AssertionError('Only disposable MySQL connections are allowed')
            return original_connect(sock, address)

        for target, replacement in [('socket.getaddrinfo', dns), ('socket.socket.connect', connect)]:
            cls.enterClassContext(patch(target, replacement))
        for key, value in {'DATABASE_URL': TEST_URL, 'FLASK_ENV': 'testing',
                           'SENTRY_DSN': '', 'CELERY_BROKER_URL': 'memory://',
                           'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
                           'LOG_FILE': '/tmp/fsi-m0-integration.log'}.items():
            cls.enterClassContext(patch.dict(os.environ, {key: value}))
        from app import create_app
        from app.config import TestingConfig
        from app.extensions import db
        cls.enterClassContext(patch.object(TestingConfig, 'SQLALCHEMY_DATABASE_URI', TEST_URL))
        cls.app = create_app('testing')
        cls.db = db
        cls.control = create_engine(url.set(database=None))
        cls.addClassCleanup(cls.control.dispose)

    def setUp(self):
        # Exact database name and hostname are guarded above; never production.
        with self.control.begin() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS `{DATABASE}`'))
            conn.execute(text(f'CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(self.db.engine.dispose)
        self.addCleanup(self.db.session.remove)

    def upgrade(self, revision='head'):
        self.db.session.remove()
        result = self.app.test_cli_runner().invoke(args=['db', 'upgrade', revision])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_empty_database_upgrades_to_current_models(self):
        self.upgrade()
        with self.db.engine.connect() as conn:
            differences = compare_metadata(MigrationContext.configure(conn), self.db.metadata)
            self.assertEqual(differences, [])
        column = next(c for c in inspect(self.db.engine).get_columns('llm_usage_log') if c['name'] == 'task_type')
        self.assertIsInstance(column['type'], String)
        self.assertNotIsInstance(column['type'], Enum)
        self.assertEqual(column['type'].length, 50)
        self.assertFalse(column['nullable'])

    def test_admin_http_candidate_roundtrips_without_activating_or_ingesting(self):
        import json
        from bs4 import BeautifulSoup
        from werkzeug.security import generate_password_hash
        from app.models.user import User
        from app.models.source import NewsSource

        self.upgrade()
        user = User(email='admin@test.invalid', is_admin=True,
                    password_hash=generate_password_hash('test-password'))
        source = NewsSource(name='Synthetic', slug='candidate', url='https://news.test.invalid/', category='national')
        self.db.session.add_all([user, source])
        self.db.session.flush()
        source_id = source.id
        self.db.session.commit()
        self.db.session.remove()
        client = self.app.test_client()

        def http(method, url, **kwargs):
            # Fresh request/ORM observation context, including Flask-Login's g.
            with self.app.app_context():
                return getattr(client, method)(url, **kwargs)

        token = BeautifulSoup(http('get', '/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')['value']
        self.assertEqual(http('post', '/auth/login', data={
            'email': 'admin@test.invalid', 'password': 'test-password', 'csrf_token': token,
        }).status_code, 302)
        recipe = {
            'format_version': 1, 'output_contract': 'article.v1', 'target_kind': 'news',
            'source_id': source_id, 'locale': 'en', 'transport': 'http', 'extractor': 'rss',
            'identity_policy': 'legacy-compatible-url-v1',
            'feed': {'url': 'https://news.test.invalid/feed?label=énergie-实验室-🚀',
                     'fields': {'title': 'title', 'url': 'link'}},
        }
        path = f'/admin/sources/{source_id}/crawl-config'
        with patch('celery.app.base.Celery.send_task', side_effect=AssertionError('No dispatch')):
            with patch('litellm.completion', side_effect=AssertionError('No model call')):
                saved = http('post', path, data={'recipe': json.dumps(recipe), 'csrf_token': token})
        self.assertEqual(saved.status_code, 302)
        page = BeautifulSoup(http('get', saved.location).text, 'html.parser')
        self.assertEqual(json.loads(page.select_one('pre[data-recipe]').get_text()), recipe)
        self.assertEqual(page.select_one('[data-version-status]').get_text(strip=True), 'Candidate')
        self.assertIn('No active recipe', http('get', path).text)
        self.assertEqual(http('get', '/api/v1/news').json['total'], 0)

    def test_old_enum_usage_and_foreign_keys_survive_upgrade(self):
        from app.models.llm import LLMUsageLog
        from app.models.source import NewsSource
        from app.models.article import Article
        self.upgrade(PREVIOUS)
        # Historical schema does not have the new role/priority columns. Seed it
        # with explicit old columns, not today's ORM constructor.
        self.db.session.execute(text("INSERT INTO llm_config (id,provider,model,tasks,is_active,is_default,created_at) VALUES (42,'synthetic','owner-choice','[\"translate\"]',1,0,NOW())"))
        source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
        self.db.session.add(source)
        self.db.session.flush()
        self.db.session.execute(text("INSERT INTO article (id,source_id,external_id,url,title_fr,llm_processed,crawled_at,created_at,updated_at) VALUES (52,:source_id,'legacy','https://test.invalid/a','Legacy article',0,NOW(),NOW(),NOW())"), {'source_id': source.id})
        config_id, article_id = 42, 52
        self.db.session.add(LLMUsageLog(config_id=config_id, article_id=article_id, task_type='translate', cost_usd='0.025'))
        self.db.session.commit()
        self.upgrade()
        for task in ['digest', 'insight', 'company_analysis']:
            self.db.session.add(LLMUsageLog(config_id=config_id, article_id=article_id, task_type=task, cost_usd='0.01'))
        self.db.session.commit()
        self.assertEqual(LLMUsageLog.query.count(), 4)
        self.assertEqual(LLMUsageLog.query.filter_by(task_type='translate').one().article_id, article_id)
        self.assertEqual(str(LLMUsageLog.query.filter_by(task_type='translate').one().cost_usd), '0.025000')
        article = Article.query.one()
        self.assertEqual(article.title_fr, 'Legacy article')
        self.assertEqual((article.content_level, article.source_language, article.crawl_provenance), (None, None, None))
        from app.models.llm import LLMConfig
        config = self.db.session.get(LLMConfig, 42)
        self.assertEqual((config.model, config.tasks, config.role, config.priority),
                         ('owner-choice', ['translate'], 'primary', 100))

    @contextmanager
    def synthetic_news_engine(self):
        """External DNS/socket/TLS fixtures, actual parser/engine and disposable MySQL."""
        import json
        from pathlib import Path
        import subprocess
        import sys
        from tempfile import TemporaryDirectory
        from app.crawlers.engine import CrawlEngine
        from app.crawlers.fetcher import FetchPolicy
        from app.models.source import NewsSource
        self.upgrade()
        source = NewsSource(name='Synthetic engine', slug='engine-mysql', url='https://news.test.invalid/news', category='regional')
        self.db.session.add(source)
        self.db.session.commit()
        doc = {'format_version': 1, 'output_contract': 'article.v1', 'target_kind': 'news',
               'source_id': source.id, 'locale': 'en', 'transport': 'http', 'identity_policy': 'legacy-compatible-url-v1',
               'list_pages': [{'url': source.url, 'item_selector': 'article', 'fields': {
                   'title': {'selector': 'a', 'read': 'text'}, 'url': {'selector': 'a', 'read': 'attr', 'attr': 'href'}}}]}
        original, processes = subprocess.Popen, []
        bootstrap = Path(__file__).resolve().parents[1] / 'support' / 'fetch_network.py'
        with TemporaryDirectory(prefix='fsi-m1-mysql-network-') as directory:
            scenario, trace = Path(directory) / 'scenario.json', Path(directory) / 'trace.jsonl'
            scenario.write_text(json.dumps({'routes': {source.url: {'body': '<article><a href="/research">Research</a></article>'}}}))
            def spawn(command, **kwargs):
                if Path(command[-1]).name == '_fetch_worker.py':
                    command = [sys.executable, '-I', str(bootstrap), command[-1], str(scenario), str(trace)]
                elif Path(command[-1]).name != '_parse_worker.py':
                    raise AssertionError('Unexpected process in engine fixture')
                process = original(command, **kwargs)
                processes.append(process)
                return process
            try:
                with patch('subprocess.Popen', spawn):
                    yield CrawlEngine(source.id, recipe=doc, fetch_policy=FetchPolicy(allowed_hosts=('news.test.invalid',), min_interval=0))
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=2)
                        self.fail('Engine leaked a helper process')

    def test_admin_http_preview_persists_report_and_source_change_stales_it(self):
        import json
        from tempfile import TemporaryDirectory
        from bs4 import BeautifulSoup
        from werkzeug.security import generate_password_hash
        from app.models.user import User

        with self.synthetic_news_engine() as fixture, TemporaryDirectory(prefix='fsi-evidence-') as directory, patch.dict(self.app.config):
            self.app.config['CRAWL_EVIDENCE_DIR'] = directory
            self.db.session.add(User(email='preview-admin@test.invalid', is_admin=True,
                                     password_hash=generate_password_hash('test-password')))
            self.db.session.commit()
            self.db.session.remove()
            client = self.app.test_client()

            def http(method, url, **kwargs):
                with self.app.app_context():
                    return getattr(client, method)(url, **kwargs)

            token = BeautifulSoup(http('get', '/auth/login').text, 'html.parser').select_one('input[name=csrf_token]')['value']
            self.assertEqual(http('post', '/auth/login', data={
                'email': 'preview-admin@test.invalid', 'password': 'test-password', 'csrf_token': token,
            }).status_code, 302)
            saved = http('post', f'/admin/sources/{fixture.source_id}/crawl-config', data={
                'recipe': json.dumps(fixture.recipe.to_dict()), 'csrf_token': token,
            })
            self.assertEqual(saved.status_code, 302)
            form = BeautifulSoup(http('get', saved.location).text, 'html.parser').select_one('form[data-preview]')
            data = {field['name']: field.get('value', '') for field in form.select('input[name]')
                    if not field.has_attr('disabled') and (field.get('type') != 'checkbox' or field.has_attr('checked'))}
            data.update(allowed_hosts='news.test.invalid', quality_kind='news', retain_evidence='1')
            with patch('celery.app.base.Celery.send_task', side_effect=AssertionError('No dispatch')):
                with patch('litellm.completion', side_effect=AssertionError('No model')):
                    result = http('post', form['action'], data=data)
            self.assertEqual(result.status_code, 302)
            report = BeautifulSoup(http('get', result.location).text, 'html.parser')
            self.assertEqual(report.select_one('[data-preview-status]').get_text(strip=True), 'ready')
            self.assertEqual(report.select_one('[data-field="title"]').get_text(strip=True), 'Research')
            self.assertEqual(report.select_one('[data-evidence-status]').get_text(strip=True), 'available')
            replay_form = report.select_one('form[data-replay]')
            replayed = http('post', replay_form['action'], data={'csrf_token': token})
            self.assertEqual(replayed.status_code, 200)
            self.assertIn('Offline snapshot replay', replayed.text)
            self.assertEqual(http('get', '/api/v1/news').json['total'], 0)
            self.assertEqual(http('post', f'/admin/sources/{fixture.source_id}/toggle', data={'csrf_token': token}).status_code, 302)
            stale = BeautifulSoup(http('get', result.location).text, 'html.parser')
            self.assertEqual(stale.select_one('[data-preview-status]').get_text(strip=True), 'stale')
            self.assertEqual(http('post', form['action'], data=data).status_code, 409)

    def test_mysql_news_engine_round_trips_quality_json_and_deduplicates(self):
        from app.models.article import Article
        with self.synthetic_news_engine() as engine:
            first, second = engine.run(), engine.run()
        # The engine owns its transactions. expire_all() would retain the
        # fixture's pre-run REPEATABLE READ snapshot and hide committed rows.
        self.db.session.remove()
        self.assertEqual((first.status, second.status), ('success', 'no_change'))
        article = Article.query.one()
        self.assertEqual(first.article_ids, (article.id,))
        self.assertEqual((article.content_level, article.source_language), ('metadata_only', 'en'))
        self.assertEqual(article.crawl_provenance['engine'], 'news-engine.v1')
        self.assertEqual(article.crawl_provenance['quality_profile']['min_content_chars'], 200)

    def test_mysql_news_engine_final_log_failure_rolls_back_article_and_source(self):
        from app.models.article import Article
        from app.models.source import NewsSource
        with self.synthetic_news_engine() as engine:
            with self.db.engine.begin() as conn:
                conn.execute(text("CREATE TRIGGER reject_crawl_completion BEFORE UPDATE ON crawl_log FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'synthetic final log failure'"))
            result = engine.run()
        # Observe rollback from a new transaction, not a stale empty snapshot.
        self.db.session.remove()
        self.assertEqual(result.status, 'failed')
        self.assertTrue(result.retryable)
        self.assertEqual(result.article_ids, ())
        self.assertEqual(Article.query.count(), 0)
        self.assertIsNone(NewsSource.query.one().last_crawled_at)

    def test_legacy_company_json_and_counter_backfill(self):
        self.upgrade('0dae407b3532')
        with self.db.engine.begin() as conn:
            conn.execute(text("INSERT INTO company (name,slug,is_grenoble,is_auto_created,created_at,updated_at,ai_analysis) VALUES ('Legacy','legacy',0,0,NOW(),NOW(),:analysis)"),
                         {'analysis': '{"overview":"original analysis"}'})
        self.upgrade()
        from app.models.company import Company
        company = Company.query.one()
        self.assertEqual(company.ai_analysis, {'overview': 'original analysis'})
        self.assertEqual(company.ai_analysis_failures, 0)

    def make_source(self):
        from app.models.source import NewsSource
        source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
        self.db.session.add(source)
        self.db.session.flush()
        source_id = source.id
        self.db.session.commit()
        self.db.session.remove()
        return source_id

    def test_mysql_crawl_duplicate_replay_and_log(self):
        from app.crawlers.base import BaseCrawler, RawArticle
        from app.models.source import NewsSource, CrawlLog
        from app.models.article import Article
        self.upgrade()
        source_id = self.make_source()
        class FixtureCrawler(BaseCrawler):
            def fetch_articles(self):
                article = RawArticle('Research', 'https://test.invalid/news', 'one')
                return [article, article]
        crawler = FixtureCrawler(self.db.session.get(NewsSource, source_id))
        self.assertEqual(crawler.run().articles_new, 1)
        self.assertEqual(crawler.run().status, 'no_change')
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual([log.status for log in CrawlLog.query.all()], ['success', 'success'])

    def test_mysql_late_write_failure_rolls_back_and_finishes_log(self):
        from app.crawlers.base import BaseCrawler, RawArticle
        from app.models.source import NewsSource, CrawlLog
        from app.models.article import Article
        self.upgrade()
        source_id = self.make_source()
        with self.db.engine.begin() as conn:
            conn.execute(text("CREATE TRIGGER m0_fail_article BEFORE INSERT ON article FOR EACH ROW BEGIN IF NEW.external_id='two' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic second write failure'; END IF; END"))
        class FixtureCrawler(BaseCrawler):
            def fetch_articles(self):
                return [RawArticle('First', 'https://test.invalid/one', 'one'),
                        RawArticle('Second', 'https://test.invalid/two', 'two')]
        result = FixtureCrawler(self.db.session.get(NewsSource, source_id)).run()
        self.assertTrue(result.errors)
        self.assertEqual(result.articles_new, 0)
        self.assertEqual(Article.query.count(), 0)
        self.assertEqual(CrawlLog.query.one().status, 'failed')
        self.assertIsNotNone(CrawlLog.query.one().finished_at)

    def test_mysql_competing_crawls_keep_one_identity(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from app.crawlers.base import BaseCrawler, RawArticle
        from app.models.source import NewsSource, CrawlLog
        from app.models.article import Article
        self.upgrade()
        source_id = self.make_source()
        barrier = Barrier(2)
        class FixtureCrawler(BaseCrawler):
            def fetch_articles(self):
                return [RawArticle('Research', 'https://test.invalid/news', 'one')]
        def before_insert(conn, cursor, statement, parameters, context, many):
            if statement.startswith('INSERT INTO article '):
                barrier.wait(timeout=10)
        def crawl():
            with self.app.app_context():
                self.db.session.execute(text('SET SESSION innodb_lock_wait_timeout=5'))
                return FixtureCrawler(self.db.session.get(NewsSource, source_id)).run()
        event.listen(self.db.engine, 'before_cursor_execute', before_insert)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [future.result(timeout=20) for future in [executor.submit(crawl), executor.submit(crawl)]]
        finally:
            event.remove(self.db.engine, 'before_cursor_execute', before_insert)
        self.assertEqual(sorted(r.articles_new for r in results), [0, 1])
        self.assertTrue(all(not r.errors for r in results))
        self.assertEqual(Article.query.count(), 1)
        self.assertEqual(CrawlLog.query.filter_by(status='success').count(), 2)

    def make_llm_article(self):
        from app.models.article import Article
        from app.models.category import Category
        from app.models.llm import LLMConfig
        self.upgrade()
        source_id = self.make_source()
        article = Article(source_id=source_id, title_fr='Synthetic title', content_fr='Synthetic research news',
                          url='https://test.invalid/llm')
        self.db.session.add_all([article, Category(name='Research', slug='research'),
                                 LLMConfig(provider='synthetic', model='test', is_default=True,
                                           tasks=['translate', 'digest', 'summarize', 'ner', 'sentiment', 'classify', 'insight'],
                                           cost_per_1k_input='0.01', cost_per_1k_output='0.02')])
        self.db.session.flush()
        article_id = article.id
        self.db.session.commit()
        self.db.session.remove()
        # Keep a regression from hanging at MySQL's usual 50-second lock timeout.
        def short_locks(connection, record, proxy):
            with connection.cursor() as cursor:
                cursor.execute('SET SESSION innodb_lock_wait_timeout=3')
        event.listen(self.db.engine, 'checkout', short_locks)
        self.addCleanup(event.remove, self.db.engine, 'checkout', short_locks)
        self.enterContext(patch('app.llm.client.redis_client', None))
        self.enterContext(patch('app.llm.circuit_breaker.redis_client', None))
        return article_id

    @staticmethod
    def llm_reply(**kwargs):
        import json
        from types import SimpleNamespace
        system = kwargs['messages'][0]['content']
        if 'Named Entity Recognition' in system:
            content = json.dumps({'companies': [{'name': 'Fixture Corp', 'mentions': 1, 'is_primary': True}]})
        elif 'sentiment analysis specialist' in system:
            content = json.dumps({'sentiment': 'positive', 'score': 0.8, 'reason': 'Research'})
        elif 'tech news classifier' in system:
            content = json.dumps({'categories': [{'category': 'research', 'confidence': 0.9}],
                                  'highlights': ['local_research'], 'event_date': None})
        else:
            content = 'Synthetic enriched text'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason='stop')],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50))

    def test_mysql_llm_independent_ledger_does_not_wait_on_business_parent(self):
        from app.llm.tasks import process_article_llm
        from app.models.article import Article, ArticleCompany, ArticleCategory
        from app.models.llm import LLMUsageLog
        article_id = self.make_llm_article()
        with patch('app.llm.client.litellm.completion', side_effect=self.llm_reply):
            process_article_llm.run(article_id)
            process_article_llm.run(article_id)
        self.db.session.remove()
        self.assertTrue(self.db.session.get(Article, article_id).llm_processed)
        self.assertEqual(ArticleCompany.query.count(), 1)
        self.assertEqual(ArticleCategory.query.count(), 1)
        self.assertEqual(LLMUsageLog.query.count(), 12)
        self.assertTrue(all(log.success and log.article_id == article_id for log in LLMUsageLog.query.all()))

    def test_mysql_llm_apply_failure_keeps_usage_but_rolls_back_business(self):
        from app.llm.tasks import process_article_llm
        from app.models.article import Article, ArticleCompany
        from app.models.company import Company
        from app.models.llm import LLMUsageLog
        article_id = self.make_llm_article()
        with self.db.engine.begin() as conn:
            conn.execute(text("CREATE TRIGGER m05_fail_category BEFORE INSERT ON article_category FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic apply failure'"))
        with patch('app.llm.client.litellm.completion', side_effect=self.llm_reply):
            with self.assertRaisesRegex(Exception, 'synthetic apply failure'):
                process_article_llm.run(article_id)
            self.db.session.remove()
            self.assertFalse(self.db.session.get(Article, article_id).llm_processed)
            self.assertEqual(Company.query.count(), 0)
            self.assertEqual(ArticleCompany.query.count(), 0)
            self.assertEqual(LLMUsageLog.query.count(), 12)
            self.db.session.remove()
            with self.db.engine.begin() as conn:
                conn.execute(text('DROP TRIGGER m05_fail_category'))
            process_article_llm.run(article_id)
        self.db.session.remove()
        self.assertTrue(self.db.session.get(Article, article_id).llm_processed)
        self.assertEqual(ArticleCompany.query.count(), 1)

    def test_mysql_duplicate_llm_consumers_apply_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from app.llm.tasks import process_article_llm
        from app.models.article import ArticleCompany, ArticleCategory
        from app.models.company import Company
        article_id = self.make_llm_article()
        barrier = Barrier(2)
        def reply(**kwargs):
            system = kwargs['messages'][0]['content']
            if 'concise tech industry analyst' in system and 'English' in system:
                barrier.wait(timeout=10)
            return self.llm_reply(**kwargs)
        def process():
            with self.app.app_context():
                process_article_llm.run(article_id)
        with patch('app.llm.client.litellm.completion', side_effect=reply):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(process), pool.submit(process)]
                for future in futures:
                    future.result(timeout=30)
        self.db.session.remove()
        self.assertEqual(Company.query.count(), 1)
        self.assertEqual(ArticleCompany.query.count(), 1)
        self.assertEqual(ArticleCategory.query.count(), 1)

    def test_existing_varchar_is_not_rewritten(self):
        self.upgrade(PREVIOUS)
        with self.db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE llm_usage_log MODIFY task_type VARCHAR(50) NOT NULL'))
        statements = []
        def record(conn, cursor, statement, parameters, context, many):
            statements.append(statement)
        event.listen(self.db.engine, 'before_cursor_execute', record)
        try:
            self.upgrade()
        finally:
            event.remove(self.db.engine, 'before_cursor_execute', record)
        self.assertFalse(any('ALTER TABLE llm_usage_log' in sql for sql in statements))
        with self.db.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT version_num FROM alembic_version')).scalar(), HEAD)


if __name__ == '__main__':
    unittest.main()
