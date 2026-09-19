"""Validation DDL does not manufacture freeze points for legacy candidates."""
from sqlalchemy import inspect, text
from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'd9b72a6e410c'
HEAD = 'e1c73d9b502a'


def test_validation_upgrade_keeps_old_history_and_does_not_create_certifications(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "old.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE crawl_learning_history (id INTEGER PRIMARY KEY, session_generation INTEGER NOT NULL, exposure_generation INTEGER NOT NULL, history_complete BOOLEAN NOT NULL)')
            conn.exec_driver_sql('INSERT INTO crawl_learning_history VALUES (1,4,7,0)')
            for name, kind in [('crawl_repair_session', 'VARCHAR(36)'), ('crawl_schema_version', 'INTEGER'), ('crawl_capture_manifest', 'INTEGER'), ('user', 'INTEGER')]:
                conn.exec_driver_sql(f'CREATE TABLE {name} (id {kind} PRIMARY KEY)')
            conn.exec_driver_sql("INSERT INTO crawl_repair_session VALUES ('legacy')")
            conn.exec_driver_sql('INSERT INTO crawl_schema_version VALUES (42)')
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT session_generation,exposure_generation,history_complete,selection_generation FROM crawl_learning_history')).one()) == (4, 7, 0, 0)
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_validation_report')).scalar_one() == 0
            assert conn.execute(text('SELECT id FROM crawl_repair_session')).scalar_one() == 'legacy'
            assert conn.execute(text('SELECT id FROM crawl_schema_version')).scalar_one() == 42
        unique = {tuple(c['column_names']) for c in inspect(db.engine).get_unique_constraints('crawl_validation_report')}
        assert {('session_id',), ('candidate_id',)} <= unique
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_validation_mysql_ddl_is_expand_only(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_validation_report' in result.output
    assert 'ADD COLUMN selection_generation INTEGER NOT NULL DEFAULT' in result.output
    assert 'FOREIGN KEY(session_id) REFERENCES crawl_repair_session (id)' in result.output
    assert 'UNIQUE (candidate_id)' in result.output
    assert 'UNIQUE (session_id)' in result.output
    for forbidden in ('UPDATE crawl_repair_session', 'UPDATE crawl_schema_version', 'INSERT INTO crawl_validation_report', 'DELETE FROM', 'DROP TABLE'):
        assert forbidden not in result.output
