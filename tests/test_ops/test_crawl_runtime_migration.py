"""Expand-only crawl runtime migration through the real Alembic CLI, not create_all."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'd3e7a1c95b28'
HEAD = 'b9d4f6a2c813'


def test_upgrade_keeps_profiles_and_logs_and_creates_empty_runtime_tables(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE crawl_source_profile (id INTEGER PRIMARY KEY, source_id INTEGER, generation INTEGER)')
            conn.exec_driver_sql('INSERT INTO crawl_source_profile VALUES (1, 7, 3)')
            conn.exec_driver_sql('CREATE TABLE crawl_log (id INTEGER PRIMARY KEY, source_id INTEGER, started_at DATETIME, status TEXT)')
            conn.exec_driver_sql("INSERT INTO crawl_log VALUES (5, 7, '2026-09-24 01:00:00', 'failed')")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text(
                'SELECT generation, active_version_id, previous_version_id, activation_generation, '
                'active_source_generation FROM crawl_source_profile')).one()) == (3, None, None, 0, None)
            assert tuple(conn.execute(text(
                'SELECT status, claim_id, fence, route, outcome, error_code FROM crawl_log')).one()) == (
                'failed', None, None, None, None, None)
            for table in ('crawl_source_state', 'crawl_schema_decision', 'article_llm_job'):
                assert conn.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
        unique = {tuple(row['column_names']) for row in inspect(db.engine).get_unique_constraints('article_llm_job')}
        assert ('active_article_id',) in unique
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_mysql_ddl_is_additive_and_backfills_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    for created in ('CREATE TABLE crawl_source_state', 'CREATE TABLE crawl_schema_decision',
                    'CREATE TABLE article_llm_job', 'UNIQUE (active_article_id)'):
        assert created in result.output
    for forbidden in ('DROP TABLE', 'DELETE FROM', 'UPDATE crawl_log', 'UPDATE crawl_source_profile',
                      'INSERT INTO crawl_source_state', 'INSERT INTO article_llm_job'):
        assert forbidden not in result.output
