import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('case,expected', [('rate_limit', 0), ('missing_task', 1), ('missing_worker', 1)])
def test_readiness_cli_understands_celery_registration_protocol(tmp_path, case, expected):
    # Captured protocol shape, not output recomputed from the implementation.
    tasks = ['app.crawlers.tasks.crawl_source',
             'app.llm.tasks.process_article_llm [rate_limit=10/m]',
             'app.email.tasks.send_daily_digest']
    if case == 'missing_task':
        tasks = tasks[1:]
    registrations = {'llm@fixture': tasks, 'fast@fixture': tasks}
    if case == 'missing_worker':
        del registrations['fast@fixture']
    fixture = tmp_path / 'registered.json'
    fixture.write_text(json.dumps(registrations))
    result = subprocess.run([sys.executable, 'scripts/check_worker_readiness.py', '--snapshot', str(fixture)],
                            cwd=ROOT, capture_output=True, text=True, timeout=5)
    assert result.returncode == expected, result.stdout + result.stderr
