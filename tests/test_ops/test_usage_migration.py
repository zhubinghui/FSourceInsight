from app import create_app
from app.config import TestingConfig


def test_full_mysql_upgrade_widens_usage_task_type(monkeypatch, tmp_path):
    # URL is only for the SQL compiler; socket guard prohibits connections.
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    result = app.test_cli_runner().invoke(args=['db', 'upgrade', '--sql'])
    assert result.exit_code == 0, result.output
    assert 'ALTER TABLE llm_usage_log MODIFY task_type VARCHAR(50) NOT NULL' in result.output
    assert 'DROP TABLE llm_usage_log' not in result.output
