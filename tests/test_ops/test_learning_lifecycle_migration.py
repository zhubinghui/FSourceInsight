"""Real Alembic CLI: preserve failures/money; quarantine, not historical certification."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'e1c73d9b502a'
HEAD = 'f8b64d2c901e'


def test_lifecycle_upgrade_quarantines_old_failures_without_resetting_work(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('CREATE TABLE crawl_repair_session (id VARCHAR(36) PRIMARY KEY, state VARCHAR(24), rounds INTEGER, cost_limit NUMERIC(18,6), deadline_at DATETIME)')
            for state in ('blocked', 'exhausted', 'cancelled', 'queued', 'running', 'awaiting_validation'):
                conn.execute(text("INSERT INTO crawl_repair_session VALUES (:id,:id,2,0.20,'2026-01-01 00:03:00')"), {'id': state})
            conn.exec_driver_sql('CREATE TABLE llm_reservation (id INTEGER PRIMARY KEY, state TEXT, reserved_usd NUMERIC(18,6))')
            conn.exec_driver_sql("INSERT INTO llm_reservation VALUES (1,'unknown',0.092160)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        with db.engine.connect() as conn:
            rows = conn.execute(text('SELECT * FROM crawl_repair_session')).mappings().all()
            for row in rows:
                assert row['rounds'] == 2 and float(row['cost_limit']) == 0.20
                assert row['deadline_at'] == '2026-01-01 00:03:00'
                assert row['retry_count'] == 0
                if row['state'] in ('blocked', 'exhausted', 'cancelled'):
                    until = datetime.fromisoformat(row['cooldown_until'])
                    assert before + timedelta(hours=6) <= until <= after + timedelta(hours=6, seconds=1)
                else:
                    assert row['cooldown_until'] is None
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_repair_retry')).scalar_one() == 0
            assert tuple(conn.execute(text('SELECT state,reserved_usd FROM llm_reservation')).one()) == ('unknown', 0.092160)
        unique = {tuple(item['column_names']) for item in inspect(db.engine).get_unique_constraints('crawl_repair_retry')}
        assert {('session_id', 'number'), ('session_id', 'after_round')} <= unique
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_lifecycle_mysql_ddl_retains_history_and_uses_utc_quarantine(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE crawl_repair_retry' in result.output
    assert 'ADD COLUMN cooldown_until DATETIME' in result.output
    assert 'ADD COLUMN retry_count INTEGER NOT NULL DEFAULT' in result.output
    assert 'UTC_TIMESTAMP()' in result.output
    assert 'FOREIGN KEY(session_id) REFERENCES crawl_repair_session (id)' in result.output
    for forbidden in ('DROP TABLE', 'DELETE FROM', 'UPDATE llm_reservation', 'INSERT INTO crawl_repair_retry'):
        assert forbidden not in result.output
