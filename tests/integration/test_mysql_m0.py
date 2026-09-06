"""Destructive tests ONLY for a disposable MySQL container/database.

Run with unittest, not against the deployment database. The runner network must
be private, with its disposable server aliased as m0-mysql and no public ports.
"""
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
HEAD = 'c821b4f7d901'
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

    def test_old_enum_usage_and_foreign_keys_survive_upgrade(self):
        from app.models.llm import LLMConfig, LLMUsageLog
        from app.models.source import NewsSource
        from app.models.article import Article
        self.upgrade(PREVIOUS)
        config = LLMConfig(provider='synthetic', model='synthetic', tasks=['translate'])
        source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
        self.db.session.add_all([config, source])
        self.db.session.flush()
        article = Article(source_id=source.id, external_id='legacy', url='https://test.invalid/a', title_fr='Legacy article')
        self.db.session.add(article)
        self.db.session.flush()
        config_id, article_id = config.id, article.id
        self.db.session.add(LLMUsageLog(config_id=config_id, article_id=article_id, task_type='translate', cost_usd='0.025'))
        self.db.session.commit()
        self.upgrade()
        for task in ['digest', 'insight', 'company_analysis']:
            self.db.session.add(LLMUsageLog(config_id=config_id, article_id=article_id, task_type=task, cost_usd='0.01'))
        self.db.session.commit()
        self.assertEqual(LLMUsageLog.query.count(), 4)
        self.assertEqual(LLMUsageLog.query.filter_by(task_type='translate').one().article_id, article_id)
        self.assertEqual(str(LLMUsageLog.query.filter_by(task_type='translate').one().cost_usd), '0.025000')
        self.assertEqual(Article.query.one().title_fr, 'Legacy article')

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
