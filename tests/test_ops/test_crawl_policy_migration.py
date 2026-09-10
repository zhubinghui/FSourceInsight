"""Policy expansion through the established Alembic/DB operations seam."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestingConfig
from app.extensions import db


HEAD = 'c9e41a7b620f'


def test_policy_migration_is_additive_mysql_sql(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'b6c2a4d9e710:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_policy_version' in result.output
    assert 'ADD COLUMN source_generation INTEGER NOT NULL DEFAULT' in result.output
    assert 'ADD COLUMN policy_generation INTEGER' in result.output
    assert 'UNIQUE (profile_id, generation)' in result.output
    assert 'document JSON NOT NULL' in result.output
    for table in ['article', 'news_source', 'crawl_log', 'crawl_schema_version', 'crawl_preview_report', 'llm_config']:
        assert not any(f'{operation} {table}' in result.output for operation in ['ALTER TABLE', 'DROP TABLE', 'UPDATE', 'INSERT INTO'])


def test_policy_expansion_preserves_old_profile_candidates_and_reports_without_granting(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('PRAGMA foreign_keys=ON')
            conn.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('INSERT INTO user VALUES (7)')
            conn.exec_driver_sql('CREATE TABLE crawl_source_profile (id INTEGER PRIMARY KEY, source_id INTEGER, generation INTEGER NOT NULL)')
            conn.exec_driver_sql('INSERT INTO crawl_source_profile VALUES (42, 8, 9)')
            conn.exec_driver_sql('CREATE TABLE crawl_schema_version (id INTEGER PRIMARY KEY, recipe JSON, status TEXT)')
            conn.exec_driver_sql("INSERT INTO crawl_schema_version VALUES (6, '{\"source_id\": 8}', 'candidate')")
            conn.exec_driver_sql('CREATE TABLE crawl_preview_report (id INTEGER PRIMARY KEY, report JSON)')
            conn.exec_driver_sql("INSERT INTO crawl_preview_report VALUES (5, '{\"format\": \"admin-preview.v1\"}')")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', 'b6c2a4d9e710']).exit_code == 0
        upgraded = runner.invoke(args=['db', 'upgrade', HEAD])
        assert upgraded.exit_code == 0, upgraded.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT generation,source_generation,policy_generation FROM crawl_source_profile')).one()) == (9, 0, None)
            assert tuple(conn.execute(text('SELECT recipe,status FROM crawl_schema_version')).one()) == ('{"source_id": 8}', 'candidate')
            assert conn.execute(text('SELECT report FROM crawl_preview_report')).scalar_one() == '{"format": "admin-preview.v1"}'
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_policy_version')).scalar_one() == 0
        assert {fk['referred_table'] for fk in inspect(db.engine).get_foreign_keys('crawl_policy_version')} == {'user', 'crawl_source_profile'}
        sql = text('INSERT INTO crawl_policy_version (id,profile_id,generation,source_generation,source_fingerprint,document,document_hash,created_by_id,created_at) '
                   'VALUES (:id,:profile,10,0,:hash,\'{}\',:hash,7,CURRENT_TIMESTAMP)')
        with db.engine.begin() as conn:
            conn.execute(sql, {'id': 1, 'profile': 42, 'hash': 'a' * 64})
        for other_profile in [42, 99]:
            with pytest.raises(IntegrityError), db.engine.begin() as conn:
                conn.execute(sql, {'id': 2, 'profile': other_profile, 'hash': 'a' * 64})
        result = runner.invoke(args=['db', 'downgrade', 'b6c2a4d9e710'])
        assert result.exit_code != 0
        assert 'retain policy history' in result.output
        assert 'crawl_policy_version' in inspect(db.engine).get_table_names()
        db.session.remove()
        db.engine.dispose()
