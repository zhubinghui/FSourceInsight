"""Expand-only capture provenance through the agreed Alembic/DB seam."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestingConfig
from app.extensions import db


HEAD = 'f2a67b904d31'


def test_capture_migration_is_additive_mysql_sql(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'c9e41a7b620f:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_capture_manifest' in result.output
    assert 'ADD COLUMN capture_generation INTEGER NOT NULL DEFAULT' in result.output
    assert 'ADD COLUMN capture_history_complete BOOL NOT NULL DEFAULT' in result.output
    assert 'UNIQUE (profile_id, sequence)' in result.output
    assert 'UNIQUE (preview_report_id)' in result.output
    assert 'document JSON NOT NULL' in result.output
    assert 'REFERENCES crawl_preview_report' not in result.output
    for table in ['article', 'news_source', 'crawl_log', 'crawl_schema_version', 'crawl_preview_report', 'crawl_policy_version', 'llm_config']:
        assert not any(f'{operation} {table}' in result.output for operation in ['ALTER TABLE', 'DROP TABLE', 'UPDATE', 'INSERT INTO'])


def test_capture_expansion_preserves_legacy_data_without_claiming_complete_history(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('PRAGMA foreign_keys=ON')
            conn.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('INSERT INTO user VALUES (7)')
            conn.exec_driver_sql('CREATE TABLE crawl_source_profile (id INTEGER PRIMARY KEY, source_id INTEGER, generation INTEGER NOT NULL, source_generation INTEGER NOT NULL, policy_generation INTEGER)')
            conn.exec_driver_sql('INSERT INTO crawl_source_profile VALUES (42, 8, 9, 2, 9)')
            conn.exec_driver_sql('CREATE TABLE crawl_schema_version (id INTEGER PRIMARY KEY, recipe JSON, status TEXT)')
            conn.exec_driver_sql("INSERT INTO crawl_schema_version VALUES (6, '{\"source_id\": 8}', 'candidate')")
            conn.exec_driver_sql('CREATE TABLE crawl_preview_report (id INTEGER PRIMARY KEY, report JSON)')
            conn.exec_driver_sql("INSERT INTO crawl_preview_report VALUES (5, '{\"format\": \"admin-preview.v1\"}')")
            conn.exec_driver_sql('CREATE TABLE crawl_policy_version (id INTEGER PRIMARY KEY, document JSON)')
            conn.exec_driver_sql("INSERT INTO crawl_policy_version VALUES (1, '{\"action\": \"revoke\"}')")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', 'c9e41a7b620f']).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.begin() as conn:
            assert tuple(conn.execute(text('SELECT generation,source_generation,policy_generation,capture_generation,capture_history_complete FROM crawl_source_profile')).one()) == (9, 2, 9, 0, 0)
            assert tuple(conn.execute(text('SELECT recipe,status FROM crawl_schema_version')).one()) == ('{"source_id": 8}', 'candidate')
            assert conn.execute(text('SELECT report FROM crawl_preview_report')).scalar_one() == '{"format": "admin-preview.v1"}'
            assert conn.execute(text('SELECT document FROM crawl_policy_version')).scalar_one() == '{"action": "revoke"}'
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_capture_manifest')).scalar_one() == 0
            # Old applications/raw SQL omit new columns: they must not claim tracking.
            conn.execute(text('INSERT INTO crawl_source_profile (id,source_id,generation,source_generation) VALUES (43,9,0,0)'))
            assert conn.execute(text('SELECT capture_history_complete FROM crawl_source_profile WHERE id=43')).scalar_one() == 0
        assert {fk['referred_table'] for fk in inspect(db.engine).get_foreign_keys('crawl_capture_manifest')} == {'user', 'crawl_source_profile', 'crawl_schema_version'}
        sql = text('INSERT INTO crawl_capture_manifest (id,profile_id,version_id,preview_report_id,sequence,document,document_hash,created_by_id,created_at) '
                   'VALUES (:id,:profile,6,:report,1,\'{}\',:hash,7,CURRENT_TIMESTAMP)')
        with db.engine.begin() as conn:
            conn.execute(sql, {'id': 1, 'profile': 42, 'report': 5, 'hash': 'a' * 64})
            conn.execute(text('DELETE FROM crawl_preview_report'))
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_capture_manifest')).scalar_one() == 1
        for profile, report in [(42, 7), (43, 5), (99, 9)]:
            with pytest.raises(IntegrityError), db.engine.begin() as conn:
                conn.execute(sql, {'id': 2, 'profile': profile, 'report': report, 'hash': 'a' * 64})
        refused = runner.invoke(args=['db', 'downgrade', 'c9e41a7b620f'])
        assert refused.exit_code != 0
        assert 'retain capture history' in refused.output
        assert 'crawl_capture_manifest' in inspect(db.engine).get_table_names()
        db.session.remove()
        db.engine.dispose()
