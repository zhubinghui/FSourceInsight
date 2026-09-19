"""Expand-only budget accounting via the agreed Alembic/isolated DB seam."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

HEAD = 'a8d31c5e7902'
PREVIOUS = 'f2a67b904d31'


def test_budget_expansion_preserves_existing_prices_usage_and_unreviewed_configs(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE user (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('CREATE TABLE llm_config (id INTEGER PRIMARY KEY, model TEXT, cost_per_1k_input NUMERIC(10,6))')
            conn.exec_driver_sql("INSERT INTO llm_config VALUES (7, 'owner-selected-model', 0.002)")
            conn.exec_driver_sql('CREATE TABLE llm_usage_log (id INTEGER PRIMARY KEY, config_id INTEGER, cost_usd NUMERIC(10,6))')
            conn.exec_driver_sql('INSERT INTO llm_usage_log VALUES (9,7,NULL), (10,7,0.123)')
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        upgraded = runner.invoke(args=['db', 'upgrade', HEAD])
        assert upgraded.exit_code == 0, upgraded.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT model,cost_per_1k_input,billing_input_limit,billing_output_limit FROM llm_config')).one()) == ('owner-selected-model', 0.002, None, None)
            assert conn.execute(text('SELECT cost_usd FROM llm_usage_log ORDER BY id')).scalars().all() == [None, 0.123]
            assert conn.execute(text('SELECT COUNT(*) FROM llm_reservation')).scalar_one() == 0
        columns = {c['name'] for c in inspect(db.engine).get_columns('llm_reconciliation')}
        assert {'reservation_id', 'actor_id', 'final_cost', 'evidence_note'} <= columns
        refused = runner.invoke(args=['db', 'downgrade', PREVIOUS])
        assert refused.exit_code != 0
        assert 'retain budget accounting' in refused.output
        db.session.remove()
        db.engine.dispose()


def test_budget_migration_mysql_sql_is_additive_without_granting_billing_authority(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'ADD COLUMN billing_input_limit INTEGER' in result.output
    assert 'ADD COLUMN billing_output_limit INTEGER' in result.output
    for table in ('llm_budget_gate', 'llm_reservation', 'llm_reconciliation'):
        assert f'CREATE TABLE {table}' in result.output
    assert 'UNIQUE (usage_id)' in result.output
    for operation in ('UPDATE llm_config', 'UPDATE llm_usage_log', 'DELETE FROM', 'DROP TABLE'):
        assert operation not in result.output
