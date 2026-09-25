"""Merge released ecology and M3 branches without rewriting either lineage."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app import create_app
from app.config import TestingConfig

HEAD = 'c7f21a9d680e'  # The merge revision under test.
CURRENT_HEAD = 'b9d4f6a2c813'


def test_one_explicit_head_preserves_both_lineages(tmp_path):
    env = {'PATH': os.environ['PATH'], 'HOME': os.environ['HOME'], 'FLASK_SKIP_DOTENV': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'LOG_FILE': str(tmp_path / 'migration.log')}
    command = [sys.executable, '-m', 'flask', '--app', 'app:create_app("testing")', 'db']
    root = Path(__file__).resolve().parents[2]
    heads = subprocess.run(command + ['heads'], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.count('(head)') == 1 and CURRENT_HEAD in heads.stdout
    history = subprocess.run(command + ['history'], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert history.returncode == 0, history.stderr
    assert all(rev in history.stdout for rev in ('b3d5e8a1c407', 'b5d81e6a430f', HEAD))


@pytest.mark.parametrize('previous,required,forbidden', [
    ('b3d5e8a1c407', 'CREATE TABLE llm_reservation', 'ADD COLUMN review_status'),
    ('b5d81e6a430f', 'ADD COLUMN review_status', 'CREATE TABLE llm_reservation'),
])
def test_mysql_upgrade_from_either_head_applies_only_the_missing_branch(
        monkeypatch, tmp_path, previous, required, forbidden):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{previous}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    assert required in result.output and forbidden not in result.output
    for sql in ('DROP TABLE', 'DELETE FROM company', 'UPDATE company SET', 'UPDATE llm_reservation SET'):
        assert sql not in result.output
