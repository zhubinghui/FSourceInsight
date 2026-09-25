"""Expand-only pause column through the real Alembic CLI."""
from sqlalchemy import text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'b9d4f6a2c813'
HEAD = 'c2e8a4f6b917'


def test_upgrade_adds_a_nullable_pause_marker_and_keeps_state_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "state.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE crawl_source_state (source_id INTEGER PRIMARY KEY, next_due_at DATETIME NOT NULL, '
                                 'due_reason VARCHAR(16) NOT NULL, fence INTEGER NOT NULL DEFAULT 0)')
            conn.exec_driver_sql("INSERT INTO crawl_source_state VALUES (7, '2026-09-25 10:00:00', 'schedule', 3)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT source_id, fence, paused_at FROM crawl_source_state')).one()) == (7, 3, None)
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_mysql_ddl_only_adds_the_column(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'ALTER TABLE crawl_source_state ADD COLUMN paused_at DATETIME' in result.output
    for forbidden in ('DROP', 'UPDATE crawl_source_state', 'DELETE FROM'):
        assert forbidden not in result.output
