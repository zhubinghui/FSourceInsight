"""Expand-only ecosystem review fields through the agreed Alembic/DB seam."""
from sqlalchemy import text

from app import create_app
from app.config import TestingConfig
from app.extensions import db


BASE, HEAD = 'f2a67b904d31', 'b3d5e8a1c407'


def test_review_migration_is_additive_mysql_sql(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{BASE}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert "ADD COLUMN review_status VARCHAR(20) NOT NULL DEFAULT 'approved'" in result.output
    for column in ['entity_type VARCHAR(30)', 'postcode VARCHAR(10)', 'city VARCHAR(120)']:
        assert f'ADD COLUMN {column}' in result.output
    assert 'ADD COLUMN local_site BOOL NOT NULL DEFAULT' in result.output
    for operation in ['DROP ', 'DELETE ', 'UPDATE company', 'INSERT INTO company']:
        assert operation not in result.output


def test_existing_and_old_application_rows_stay_visible(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE company (id INTEGER PRIMARY KEY, name TEXT, slug TEXT, is_grenoble BOOLEAN)')
            conn.exec_driver_sql("INSERT INTO company VALUES (1, 'Soitec', 'soitec', 1)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', BASE]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.begin() as conn:
            # An old application omits the new columns; its rows must not vanish from the map.
            conn.execute(text("INSERT INTO company (id,name,slug,is_grenoble) VALUES (2,'Lynred','lynred',1)"))
            rows = conn.execute(text('SELECT review_status,local_site,entity_type,postcode,city FROM company ORDER BY id')).all()
        assert [tuple(row) for row in rows] == [('approved', 0, None, None, None)] * 2
        refused = runner.invoke(args=['db', 'downgrade', BASE])
        assert refused.exit_code != 0
        assert 'retain review decisions' in refused.output
        db.session.remove()
        db.engine.dispose()
