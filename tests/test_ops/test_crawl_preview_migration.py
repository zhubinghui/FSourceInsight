"""Additive preview-report storage through the established Alembic seam."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db


def test_preview_report_migration_is_additive_mysql_sql(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', 'a731c9e25d80:b6c2a4d9e710', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_preview_report' in result.output
    assert 'report JSON NOT NULL' in result.output
    assert 'FOREIGN KEY(version_id) REFERENCES crawl_schema_version (id)' in result.output
    for table in ['article', 'news_source', 'crawl_log', 'crawl_source_profile', 'crawl_schema_version', 'llm_config']:
        assert not any(f'{operation} {table}' in result.output for operation in ['ALTER TABLE', 'DROP TABLE', 'UPDATE', 'INSERT INTO'])


def test_preview_expansion_keeps_candidates_and_refuses_destructive_rollback(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    application = create_app('testing')
    with application.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('PRAGMA foreign_keys=ON')
            conn.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('CREATE TABLE crawl_schema_version (id INTEGER PRIMARY KEY, recipe JSON, status TEXT)')
            conn.exec_driver_sql("INSERT INTO crawl_schema_version VALUES (42, '{\"source_id\": 7}', 'candidate')")
        runner = application.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', 'a731c9e25d80']).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', 'b6c2a4d9e710'])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT recipe,status FROM crawl_schema_version')).one()) == ('{"source_id": 7}', 'candidate')
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_preview_report')).scalar() == 0
        assert {fk['referred_table'] for fk in inspect(db.engine).get_foreign_keys('crawl_preview_report')} == {'user', 'crawl_schema_version'}
        result = runner.invoke(args=['db', 'downgrade', 'a731c9e25d80'])
        assert result.exit_code != 0
        assert 'retain preview history' in result.output
        assert 'crawl_preview_report' in inspect(db.engine).get_table_names()
        db.session.remove()
        db.engine.dispose()
