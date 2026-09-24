"""Expand-only refresh-job migration through real Alembic CLI, not create_all."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'c7f21a9d680e'
HEAD = 'd3e7a1c95b28'


def test_upgrade_keeps_companies_and_uncertain_money_without_backfilling_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT, ai_analysis TEXT)')
            conn.exec_driver_sql("""INSERT INTO company VALUES (1,'Analysed company','{"overview":"kept"}')""")
            conn.exec_driver_sql('CREATE TABLE llm_reservation (id VARCHAR(36) PRIMARY KEY, state TEXT, reserved_usd NUMERIC(18,6))')
            conn.exec_driver_sql("INSERT INTO llm_reservation VALUES ('old-reservation','unknown',0.092160)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT name,ai_analysis FROM company')).one()) == (
                'Analysed company', '{"overview":"kept"}')
            assert tuple(conn.execute(text('SELECT state,reserved_usd,company_refresh_id FROM llm_reservation')).one()) == (
                'unknown', 0.092160, None)
            assert conn.execute(text('SELECT count(*) FROM company_refresh_job')).scalar_one() == 0
        unique = {tuple(row['column_names']) for row in inspect(db.engine).get_unique_constraints('company_refresh_job')}
        assert ('active_company_id',) in unique
        assert all(fk['options'].get('ondelete') == 'SET NULL' for fk in inspect(db.engine).get_foreign_keys('company_refresh_job'))
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_mysql_ddl_is_additive_and_never_backfills_paid_work(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE company_refresh_job' in result.output
    assert 'UNIQUE (active_company_id)' in result.output
    assert 'FOREIGN KEY(company_refresh_id) REFERENCES company_refresh_job (id)' in result.output
    assert result.output.count('ON DELETE SET NULL') == 2
    for forbidden in ('DROP TABLE', 'DELETE FROM', 'UPDATE company', 'UPDATE llm_reservation', 'INSERT INTO company_refresh_job'):
        assert forbidden not in result.output
