from sqlalchemy import text

from app import create_app
from app.config import TestingConfig
from app.extensions import db


def test_routing_migration_keeps_existing_selection_and_usage(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE llm_config (id INTEGER PRIMARY KEY, provider TEXT, model TEXT, tasks JSON, is_active BOOLEAN, is_default BOOLEAN)'))
            conn.execute(text("INSERT INTO llm_config VALUES (42, 'custom', 'owner-choice', '[\"ner\"]', 1, 0)"))
            conn.execute(text('CREATE TABLE llm_usage_log (id INTEGER PRIMARY KEY, config_id INTEGER, cost_usd NUMERIC)'))
            conn.execute(text('INSERT INTO llm_usage_log VALUES (1, 42, 0.25)'))
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', 'c821b4f7d901']).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade'])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            row = conn.execute(text('SELECT model,tasks,role,priority FROM llm_config WHERE id=42')).one()
            assert tuple(row) == ('owner-choice', '["ner"]', 'primary', 100)
            assert conn.execute(text('SELECT cost_usd FROM llm_usage_log')).scalar() == 0.25
        db.session.remove()
        db.engine.dispose()


def test_mysql_routing_migration_is_additive(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'ADD COLUMN `role` VARCHAR(16)' in result.output
    assert 'ADD COLUMN priority INTEGER' in result.output
    assert 'UPDATE llm_config' not in result.output
