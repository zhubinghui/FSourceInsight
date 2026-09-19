"""Real CLI execution; replace only Celery control and OS exec/mount boundaries."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/learning_worker.py'
NODE = 'learn@fixture'


def snapshot():
    return {
        'registered': {NODE: ['app.crawlers.learning_tasks.learn', 'app.crawlers.learning_tasks.recover']},
        'active_queues': {NODE: [{'name': 'crawl_learn', 'routing_key': 'crawl_learn',
                                 'exchange': {'name': 'crawl_learn', 'type': 'direct'}}]},
        'stats': {NODE: {'prefetch_count': 1, 'pool': {'implementation': 'celery.concurrency.prefork:TaskPool',
            'max-concurrency': 1, 'processes': [123], 'max-tasks-per-child': 50, 'timeouts': [180, 195]}}},
    }


def test_snapshot_checks_actual_learning_queue_and_prefork_not_just_registration(tmp_path):
    path = tmp_path / 'status.json'
    path.write_text(json.dumps(snapshot()))
    result = subprocess.run([sys.executable, str(SCRIPT), 'check', '--snapshot', str(path), '--node', NODE],
                            cwd=ROOT, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'SNAPSHOT_LEARNING_WORKER_READY'


def invoke(monkeypatch, *args):
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), *args])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(SCRIPT), run_name='__main__')
    return result.value.code


@pytest.fixture
def runtime(app, db, monkeypatch, tmp_path):
    from app.config import TestingConfig
    assert app.test_cli_runner().invoke(args=['db', 'stamp', 'head']).exit_code == 0
    directory = tmp_path / 'private-evidence'
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(TestingConfig, 'CRAWL_LEARNING_ENABLED', True)
    monkeypatch.setattr(TestingConfig, 'CRAWL_EVIDENCE_DIR', str(directory))
    # Model only mount flags; real path/open/UID/permission checks remain intact.
    monkeypatch.setattr(os, 'fstatvfs', lambda fd: SimpleNamespace(f_flag=os.ST_RDONLY))
    return directory


def test_live_check_reads_only_local_schema_mount_and_targeted_worker_control(
        runtime, db, monkeypatch, capsys):
    from celery.app.control import Inspect
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    seen, sql = [], []
    data = snapshot()
    for name in ('registered', 'active_queues', 'stats'):
        def response(self, name=name):
            assert self.destination == [NODE] and self.timeout <= 3
            seen.append(name)
            return data[name]
        monkeypatch.setattr(Inspect, name, response)
    def observe(conn, cursor, statement, parameters, context, many):
        sql.append(statement)
    event.listen(Engine, 'before_cursor_execute', observe)
    try:
        assert invoke(monkeypatch, 'check', '--node', NODE) == 0
    finally:
        event.remove(Engine, 'before_cursor_execute', observe)
    assert any('alembic_version' in s for s in sql)
    assert set(seen) == {'registered', 'active_queues', 'stats'}
    assert not any(s.startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ')) for s in sql)
    assert 'LEARNING_WORKER_READY' in capsys.readouterr().out


COMMAND = ['celery', '-A', 'celery_app', 'worker', '-l', 'info', '-Q', 'crawl_learn', '-c', '1',
           '-n', 'learn@%h', '--pool=prefork', '--prefetch-multiplier=1', '--max-tasks-per-child=50',
           '--max-memory-per-child=393216', '--soft-time-limit=180', '--time-limit=195']


def test_startup_checks_local_preconditions_before_handing_off_to_celery(runtime, monkeypatch):
    executed = []
    monkeypatch.setattr(os, 'execvp', lambda executable, args: executed.append((executable, args)))
    assert invoke(monkeypatch, 'run', *COMMAND) == 0
    assert executed == [('celery', COMMAND)]


@pytest.mark.parametrize('problem', ['disabled', 'writable', 'permissions', 'symlink', 'missing', 'old_schema', 'no_schema'])
@pytest.mark.parametrize('mode', ['run', 'check'])
def test_bad_local_preconditions_never_start_or_query_a_worker(
        runtime, db, monkeypatch, capsys, problem, mode):
    from app.config import TestingConfig
    from celery.app.control import Inspect
    if problem == 'disabled':
        monkeypatch.setattr(TestingConfig, 'CRAWL_LEARNING_ENABLED', False)
    elif problem == 'writable':
        monkeypatch.setattr(os, 'fstatvfs', lambda fd: SimpleNamespace(f_flag=0))
    elif problem == 'permissions':
        runtime.chmod(0o755)
    elif problem == 'symlink':
        link = runtime.parent / 'PRIVATE_EVIDENCE_LINK'
        link.symlink_to(runtime, target_is_directory=True)
        monkeypatch.setattr(TestingConfig, 'CRAWL_EVIDENCE_DIR', str(link))
    elif problem == 'missing':
        runtime.rmdir()
    else:
        with db.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE alembic_version SET version_num='f2a67b904d31'" if problem == 'old_schema'
                                 else 'DROP TABLE alembic_version')
    calls = []
    monkeypatch.setattr(os, 'execvp', lambda *args: calls.append('exec'))
    monkeypatch.setattr(Inspect, 'registered', lambda *args, **kw: calls.append('broker'))
    args = ['run', *COMMAND] if mode == 'run' else ['check', '--node', NODE]
    assert invoke(monkeypatch, *args) == 1
    assert not calls
    out = capsys.readouterr()
    assert out.out.strip().endswith('LEARNING_WORKER_NOT_READY')
    assert str(runtime) not in out.out + out.err and 'PRIVATE_EVIDENCE_LINK' not in out.out + out.err


@pytest.mark.parametrize('problem', ['missing_task', 'other_node', 'wrong_queue', 'extra_queue', 'wrong_exchange',
                                    'solo', 'concurrency', 'process_count', 'prefetch', 'no_recycling', 'no_timeouts',
                                    'no_reply', 'malformed'])
def test_snapshot_rejects_incomplete_or_wrong_consumer(tmp_path, monkeypatch, capsys, problem):
    data = snapshot()
    if problem == 'missing_task':
        data['registered'][NODE] = ['app.crawlers.learning_tasks.learn']
    elif problem == 'other_node':
        data['stats']['learn@another'] = data['stats'].pop(NODE)
    elif problem in ('wrong_queue', 'extra_queue', 'wrong_exchange'):
        queue = data['active_queues'][NODE][0]
        if problem == 'wrong_queue':
            queue['name'] = 'crawl'
        elif problem == 'extra_queue':
            data['active_queues'][NODE].append(dict(queue, name='llm'))
        else:
            queue['exchange']['name'] = 'celery'
    elif problem == 'solo':
        data['stats'][NODE]['pool']['implementation'] = 'celery.concurrency.solo:TaskPool'
    elif problem == 'concurrency':
        data['stats'][NODE]['pool']['max-concurrency'] = 2
    elif problem == 'process_count':
        data['stats'][NODE]['pool']['processes'] = [123, 124]
    elif problem == 'prefetch':
        data['stats'][NODE]['prefetch_count'] = 4
    elif problem == 'no_recycling':
        data['stats'][NODE]['pool']['max-tasks-per-child'] = 'N/A'
    elif problem == 'no_timeouts':
        data['stats'][NODE]['pool']['timeouts'] = [0, 0]
    elif problem == 'no_reply':
        data['registered'] = None
    else:
        data = ['PRIVATE_PAYLOAD']
    path = tmp_path / 'status.json'
    path.write_text(json.dumps(data))
    assert invoke(monkeypatch, 'check', '--snapshot', str(path), '--node', NODE) == 1
    assert 'PRIVATE_PAYLOAD' not in capsys.readouterr().out


@pytest.mark.parametrize('content', ['not-json PRIVATE_SECRET', '{"stats":{},"stats":{}}',
                                   '{"stats":NaN}', '[' * 5000, 'x' * 65537])
def test_snapshot_parse_failures_are_bounded_and_private(tmp_path, monkeypatch, capsys, content):
    path = tmp_path / 'PRIVATE_SNAPSHOT'
    path.write_text(content)
    assert invoke(monkeypatch, 'check', '--snapshot', str(path), '--node', NODE) == 1
    result = capsys.readouterr()
    assert result.out.strip() == 'SNAPSHOT_LEARNING_WORKER_NOT_READY' and not result.err


def test_failed_broker_control_is_not_ready_and_never_prints_the_exception(runtime, monkeypatch, capsys):
    from celery.app.control import Inspect
    def unavailable(*args, **kwargs):
        raise OSError('PRIVATE_BROKER_SECRET')
    monkeypatch.setattr(Inspect, 'registered', unavailable)
    assert invoke(monkeypatch, 'check', '--node', NODE) == 1
    result = capsys.readouterr()
    assert 'PRIVATE_BROKER_SECRET' not in result.out + result.err


@pytest.mark.parametrize('change', ['queue', 'concurrency', 'extra', 'other_app'])
def test_startup_refuses_commands_outside_the_learning_contract(runtime, monkeypatch, change):
    command = list(COMMAND)
    if change == 'queue':
        command[command.index('-Q') + 1] = 'crawl,llm,email'
    elif change == 'concurrency':
        command[command.index('-c') + 1] = '2'
    elif change == 'other_app':
        command[command.index('-A') + 1] = 'another_app'
    else:
        command.append('--purge')
    calls = []
    monkeypatch.setattr(os, 'execvp', lambda *args: calls.append(args))
    assert invoke(monkeypatch, 'run', *command) == 1
    assert not calls
