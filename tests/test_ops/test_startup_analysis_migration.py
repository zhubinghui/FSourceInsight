"""Expand-only migration through real Alembic CLI, not create_all."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'f8b64d2c901e'
HEAD = 'a2f6d9b3107c'


def test_upgrade_preserves_legacy_companies_sources_and_uncertain_money(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT, ai_analysis_failures INTEGER)')
            conn.exec_driver_sql("INSERT INTO company VALUES (1,'Old company',3)")
            conn.exec_driver_sql('CREATE TABLE startup_source (id INTEGER PRIMARY KEY, url TEXT, is_active BOOLEAN)')
            conn.exec_driver_sql("INSERT INTO startup_source VALUES (2,'https://old.example.test',0)")
            conn.exec_driver_sql('CREATE TABLE llm_reservation (id VARCHAR(36) PRIMARY KEY, state TEXT, reserved_usd NUMERIC(18,6))')
            conn.exec_driver_sql("INSERT INTO llm_reservation VALUES ('old-reservation','unknown',0.092160)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT name,ai_analysis_failures,analysis_generation FROM company')).one()) == ('Old company', 3, 0)
            assert tuple(conn.execute(text('SELECT is_active,analysis_generation FROM startup_source')).one()) == (0, 0)
            assert tuple(conn.execute(text('SELECT state,reserved_usd,startup_analysis_id FROM llm_reservation')).one()) == ('unknown', 0.092160, None)
            assert conn.execute(text('SELECT count(*) FROM startup_analysis_job')).scalar_one() == 0
        unique = {tuple(row['column_names']) for row in inspect(db.engine).get_unique_constraints('startup_analysis_job')}
        assert ('company_id',) in unique
        assert all(fk['options'].get('ondelete') == 'SET NULL' for fk in inspect(db.engine).get_foreign_keys('startup_analysis_job'))
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_mysql_ddl_is_additive_and_never_backfills_paid_work(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'CREATE TABLE startup_analysis_job' in result.output
    assert result.output.count('ADD COLUMN analysis_generation INTEGER NOT NULL DEFAULT') == 2
    assert 'FOREIGN KEY(startup_analysis_id) REFERENCES startup_analysis_job (id)' in result.output
    assert result.output.count('ON DELETE SET NULL') == 2
    for forbidden in ('DROP TABLE', 'DELETE FROM', 'UPDATE company', 'UPDATE startup_source', 'INSERT INTO startup_analysis_job'):
        assert forbidden not in result.output
