"""Existing Alembic command seam; no service is contacted by offline SQL."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import TestingConfig
from app.extensions import db


def test_candidate_migration_mysql_sql_only_adds_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', 'e6a91f4c820d:a731c9e25d80', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_source_profile' in result.output
    assert 'CREATE TABLE crawl_schema_version' in result.output
    assert 'FOREIGN KEY(source_id) REFERENCES news_source (id)' in result.output
    assert 'FOREIGN KEY(created_by_id) REFERENCES user (id)' in result.output
    assert 'recipe JSON NOT NULL' in result.output
    assert 'UNIQUE (source_id)' in result.output
    for table in ['article', 'news_source', 'crawl_log', 'llm_config']:
        assert not any(f'{operation} {table}' in result.output for operation in ['ALTER TABLE', 'DROP TABLE', 'UPDATE', 'INSERT INTO'])


def test_candidate_expansion_preserves_existing_rows_and_foreign_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    application = create_app('testing')
    with application.app_context():
        # Minimal pre-existing dependencies, not a claim of full historical MySQL DDL.
        with db.engine.begin() as conn:
            conn.exec_driver_sql('PRAGMA foreign_keys=ON')
            conn.exec_driver_sql('CREATE TABLE news_source (id INTEGER PRIMARY KEY, url TEXT)')
            conn.exec_driver_sql("INSERT INTO news_source VALUES (42, 'https://legacy.test.invalid/')")
            conn.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('INSERT INTO user VALUES (7)')
            conn.exec_driver_sql('CREATE TABLE article (id INTEGER PRIMARY KEY, external_id TEXT, content_fr TEXT)')
            conn.exec_driver_sql("INSERT INTO article VALUES (52, 'original-guid', 'Original body')")
            conn.exec_driver_sql('CREATE TABLE crawl_log (id INTEGER PRIMARY KEY, status TEXT)')
            conn.exec_driver_sql("INSERT INTO crawl_log VALUES (62, 'success')")
        runner = application.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', 'e6a91f4c820d']).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', 'a731c9e25d80'])
        assert result.exit_code == 0, result.output
        with db.engine.begin() as conn:
            assert conn.execute(text('SELECT external_id,content_fr FROM article WHERE id=52')).one() == ('original-guid', 'Original body')
            assert conn.execute(text('SELECT status FROM crawl_log WHERE id=62')).scalar() == 'success'
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_source_profile')).scalar() == 0
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_schema_version')).scalar() == 0
            conn.exec_driver_sql('INSERT INTO crawl_source_profile (id,source_id,generation) VALUES (1,42,0)')
        with pytest.raises(IntegrityError), db.engine.begin() as conn:
            conn.exec_driver_sql('INSERT INTO crawl_source_profile (id,source_id,generation) VALUES (2,42,0)')
        with pytest.raises(IntegrityError), db.engine.begin() as conn:
            conn.exec_driver_sql('INSERT INTO crawl_source_profile (id,source_id,generation) VALUES (3,999,0)')
        assert {fk['referred_table'] for fk in inspect(db.engine).get_foreign_keys('crawl_schema_version')} == {'user', 'crawl_source_profile'}
        result = runner.invoke(args=['db', 'downgrade', 'e6a91f4c820d'])
        assert result.exit_code != 0
        assert 'retain candidate history' in result.output, result.output
        assert 'crawl_schema_version' in inspect(db.engine).get_table_names()
        db.session.remove()
        db.engine.dispose()
