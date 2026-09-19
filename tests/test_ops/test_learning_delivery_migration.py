"""Real expand-only Alembic CLI, including deliberately unconfigured old rows."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'a2f6d9b3107c'
HEAD = 'b5d81e6a430f'


def test_old_intents_get_no_invented_delivery_permission(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "old.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE crawl_repair_session (id TEXT PRIMARY KEY, state TEXT, rounds INTEGER, input_hash TEXT, retry_count INTEGER, deadline_at DATETIME, cost_limit NUMERIC(18,6))')
            for state in ('queued', 'running', 'blocked', 'awaiting_validation'):
                conn.execute(text('INSERT INTO crawl_repair_session VALUES (:state,:state,2,\'old-hash\',1,\'2026-09-19 12:03:00\',0.20)'), {'state': state})
            conn.exec_driver_sql('CREATE TABLE llm_reservation (id TEXT PRIMARY KEY, state TEXT, reserved_usd NUMERIC(18,6))')
            conn.exec_driver_sql("INSERT INTO llm_reservation VALUES ('old','unknown',0.092160)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            rows = conn.execute(text('SELECT id,state,rounds,input_hash,retry_count,deadline_at,cost_limit,dispatch_due_at FROM crawl_repair_session ORDER BY id')).all()
            assert [tuple(row) for row in rows] == [(state, state, 2, 'old-hash', 1, '2026-09-19 12:03:00', .2, None)
                for state in ('awaiting_validation', 'blocked', 'queued', 'running')]
            assert tuple(conn.execute(text('SELECT * FROM llm_reservation')).one()) == ('old', 'unknown', .092160)
        column = next(row for row in inspect(db.engine).get_columns('crawl_repair_session') if row['name'] == 'dispatch_due_at')
        assert column['nullable'] and column['default'] is None
        indexes = {row['name']: row['column_names'] for row in inspect(db.engine).get_indexes('crawl_repair_session')}
        assert indexes['idx_repair_dispatch_due'] == ['state', 'dispatch_due_at']
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_mysql_ddl_never_backfills_or_reopens_old_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'ADD COLUMN dispatch_due_at DATETIME' in result.output
    assert 'CREATE INDEX idx_repair_dispatch_due ON crawl_repair_session (state, dispatch_due_at)' in result.output
    for forbidden in ('DROP TABLE', 'DELETE FROM', 'UPDATE crawl_repair_session', 'INSERT INTO crawl_repair_session', ' DEFAULT ', 'NOT NULL'):
        assert forbidden not in result.output
