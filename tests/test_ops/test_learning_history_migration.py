"""Upgrade must preserve old evidence/money without certifying lost history."""
import pytest
from sqlalchemy import inspect, text
from app import create_app
from app.config import TestingConfig
from app.extensions import db

HEAD = 'd9b72a6e410c'
PREVIOUS = 'c4e92f7a610b'


@pytest.mark.parametrize('legacy', ['none', 'session', 'usage_only'])
def test_history_migration_certifies_only_empty_controlled_workflow(monkeypatch, tmp_path, legacy):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "old.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE crawl_repair_session (id VARCHAR(36) PRIMARY KEY, state VARCHAR(24))')
            conn.exec_driver_sql('CREATE TABLE crawl_repair_attempt (id VARCHAR(36) PRIMARY KEY, session_id VARCHAR(36), exposure JSON)')
            conn.exec_driver_sql('CREATE TABLE llm_reservation (id VARCHAR(36) PRIMARY KEY, task_type VARCHAR(50), reserved_usd NUMERIC(18,6), state VARCHAR(16))')
            conn.exec_driver_sql('CREATE TABLE llm_usage_log (id INTEGER PRIMARY KEY, task_type VARCHAR(50))')
            if legacy == 'session':
                conn.exec_driver_sql("INSERT INTO crawl_repair_session VALUES ('old-session', 'blocked')")
                conn.exec_driver_sql("INSERT INTO crawl_repair_attempt VALUES ('old-attempt', 'old-session', '[]')")
                conn.exec_driver_sql("INSERT INTO llm_reservation VALUES ('old-permit', 'crawl_schema', 0.123456, 'unknown')")
            elif legacy == 'usage_only':
                conn.exec_driver_sql("INSERT INTO llm_usage_log VALUES (1,'crawl_schema')")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            row = conn.execute(text('SELECT session_generation,exposure_generation,history_complete FROM crawl_learning_history WHERE id=1')).one()
            assert tuple(row) == ((1, 1, 0) if legacy == 'session' else (0, 0, int(legacy == 'none')))
            if legacy == 'session':
                assert tuple(conn.execute(text('SELECT state,history_sequence,input_hash FROM crawl_repair_session')).one()) == ('blocked', None, None)
                assert tuple(conn.execute(text('SELECT exposure,exposure_sequence,exposure_hash FROM crawl_repair_attempt')).one()) == ('[]', None, None)
                assert tuple(conn.execute(text('SELECT reserved_usd,state FROM llm_reservation')).one()) == (0.123456, 'unknown')
            if legacy == 'usage_only':
                assert conn.execute(text('SELECT task_type FROM llm_usage_log')).scalar_one() == 'crawl_schema'
        assert {'exposure_sequence', 'exposure_hash'} <= {c['name'] for c in inspect(db.engine).get_columns('crawl_repair_attempt')}
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_history_mysql_ddl_is_additive_and_never_rewrites_old_exposures(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_learning_history' in result.output
    assert 'ADD COLUMN history_sequence INTEGER' in result.output
    assert 'ADD COLUMN exposure_sequence INTEGER' in result.output
    assert 'UNIQUE (history_sequence)' in result.output
    assert 'UNIQUE (exposure_sequence)' in result.output
    assert 'INSERT INTO crawl_learning_history' in result.output
    for command in ('UPDATE crawl_repair_session', 'UPDATE crawl_repair_attempt', 'UPDATE llm_reservation', 'DROP TABLE', 'DELETE FROM'):
        assert command not in result.output
