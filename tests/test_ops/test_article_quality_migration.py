from sqlalchemy import text
from app import create_app
from app.config import TestingConfig
from app.extensions import db


def test_article_quality_migration_preserves_unknown_legacy_data(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE article (id INTEGER PRIMARY KEY, external_id TEXT, title_fr TEXT, content_fr TEXT)'))
            conn.execute(text("INSERT INTO article VALUES (42, 'legacy-guid', 'Original title', 'Original body')"))
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', 'd472ac9e6102']).exit_code == 0
        # This fixture represents only the M1 article expansion, not later tables.
        result = runner.invoke(args=['db', 'upgrade', 'e6a91f4c820d'])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            row = conn.execute(text('SELECT external_id,content_fr,content_level,source_language,crawl_provenance FROM article')).one()
            assert tuple(row) == ('legacy-guid', 'Original body', None, None, None)
        db.session.remove()
        db.engine.dispose()
