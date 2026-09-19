"""Expand-only learning storage through Alembic, without certifying old history."""
from sqlalchemy import inspect, text
from app import create_app
from app.config import TestingConfig
from app.extensions import db

HEAD = 'c4e92f7a610b'
PREVIOUS = 'a8d31c5e7902'


def test_learning_expansion_keeps_pending_money_and_does_not_create_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            for table in ('user', 'news_source', 'crawl_schema_version', 'crawl_capture_manifest'):
                conn.exec_driver_sql(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY)')
            conn.exec_driver_sql('CREATE TABLE llm_reservation (id VARCHAR(36) PRIMARY KEY, state VARCHAR(16), reserved_usd NUMERIC(18,6))')
            conn.exec_driver_sql("INSERT INTO llm_reservation VALUES ('old', 'unknown', 0.123456)")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        upgraded = runner.invoke(args=['db', 'upgrade', HEAD])
        assert upgraded.exit_code == 0, upgraded.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text('SELECT state,reserved_usd,learning_attempt_id FROM llm_reservation')).one()) == ('unknown', 0.123456, None)
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_repair_session')).scalar_one() == 0
            assert conn.execute(text('SELECT COUNT(*) FROM crawl_repair_attempt')).scalar_one() == 0
        assert {'exposure', 'prompt_hash', 'candidate_id'} <= {c['name'] for c in inspect(db.engine).get_columns('crawl_repair_attempt')}
        assert 'protocol_version' in {c['name'] for c in inspect(db.engine).get_columns('crawl_repair_session')}
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_learning_mysql_ddl_and_queue_registration_are_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    for table in ('crawl_repair_session', 'crawl_repair_attempt'):
        assert f'CREATE TABLE {table}' in result.output
    assert 'ADD COLUMN learning_attempt_id VARCHAR(36)' in result.output
    assert 'UNIQUE (capture_id)' in result.output
    for operation in ('UPDATE llm_config', 'UPDATE crawl_source_profile', 'DELETE FROM', 'DROP TABLE'):
        assert operation not in result.output
    from celery_app import celery, make_celery
    assert not any(job['task'] == 'app.crawlers.learning_tasks.recover' for job in celery.conf.beat_schedule.values())
    enabled_app = create_app('testing')
    enabled_app.config['CRAWL_LEARNING_ENABLED'] = True
    celery = make_celery(enabled_app)
    assert 'app.crawlers.learning_tasks' in celery.conf.include
    assert celery.conf.task_routes['app.crawlers.learning_tasks.*']['queue'] == 'crawl_learn'
    assert any(job['task'] == 'app.crawlers.learning_tasks.recover' for job in celery.conf.beat_schedule.values())
