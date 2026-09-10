"""Explicit Linux/Redis/MySQL gate using production Compose-exported commands.

Run separately from pytest; no production tasks/API are added. All HTTP calls
use the real Admin application and all work runs through the real Redis broker.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commands', type=Path, required=True)
    args = parser.parse_args()
    assert sys.platform == 'linux', 'Linux RSS and prefork verification required'
    url = make_url(os.environ['FSI_MYSQL_TEST_URL'])
    assert url.host == 'm0-mysql' and url.database == 'fsource_m0_validation'
    assert os.environ.get('FSI_DESTRUCTIVE_TESTS') == '1'
    assert os.environ['CELERY_BROKER_URL'] == 'redis://worker-redis:6379/1'
    assert os.environ['REDIS_URL'] == 'redis://worker-redis:6379/0'
    os.environ.update(DATABASE_URL=os.environ['FSI_MYSQL_TEST_URL'], FLASK_ENV='production',
                      LITELLM_LOCAL_MODEL_COST_MAP='True', SENTRY_DSN='',
                      SECRET_KEY='synthetic-worker-validation-not-a-production-secret')
    # Independent exact-name database; never import the app with a production URL.
    control = create_engine(url.set(database=None), pool_pre_ping=True)
    with control.begin() as connection:
        connection.execute(text('DROP DATABASE IF EXISTS fsource_m0_validation'))
        connection.execute(text('CREATE DATABASE fsource_m0_validation CHARACTER SET utf8mb4'))
    control.dispose()
    root = Path(tempfile.mkdtemp(prefix='fsi-worker-'))
    os.environ['FSI_WORKER_STATE'] = str(root)
    project = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(project / 'tests' / 'support'), str(project)]
    os.environ['PYTHONPATH'] = os.pathsep.join(sys.path[:2])
    # Guard real sockets in the HTTP driver too; children bootstrap identically.
    from worker_environment import celery
    from app import create_app
    from app.extensions import db
    from app.models.user import User
    from celery.signals import before_task_publish
    from flask_migrate import upgrade
    import redis
    from werkzeug.security import generate_password_hash

    app = create_app('production')
    with app.app_context():
        upgrade()
        admin = User(email='worker@example.invalid', name='Worker validation', is_admin=True, is_active_user=True,
                     password_hash=generate_password_hash('synthetic-password'))
        db.session.add(admin)
        db.session.commit()
    cache = redis.Redis.from_url(os.environ['CELERY_BROKER_URL'])
    cache.flushdb()  # Guarded disposable broker only; cannot address production.
    client = app.test_client()

    def csrf(path):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True))
        assert match, 'Real CSRF token required'
        return match.group(1)

    assert client.post('/auth/login', data={'csrf_token': csrf('/auth/login'),
                                          'email': 'worker@example.invalid', 'password': 'synthetic-password'}).status_code == 302
    assert client.post('/admin/sources/new', data={'csrf_token': csrf('/admin/sources/new'),
                      'name': 'Lifecycle fixture', 'slug': 'worker-lifecycle', 'url': 'https://news.test.invalid/',
                      'feed_url': 'https://news.test.invalid/feed', 'feed_type': 'rss'}).status_code == 302
    page = client.get('/admin/sources').get_data(as_text=True)
    source_id = re.search(r'/admin/sources/(\d+)/crawl-now', page).group(1)
    published = []

    def observe_publish(headers=None, **kwargs):
        published.append(headers['id'])

    before_task_publish.connect(observe_publish, weak=False)

    def dispatch():
        before = len(published)
        response = client.post(f'/admin/sources/{source_id}/crawl-now', data={'csrf_token': csrf('/admin/sources')})
        assert response.status_code == 302 and len(published) == before + 1
        return celery.AsyncResult(published[-1])

    def wait_for(callback, label, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = callback()
            if value:
                return value
            time.sleep(0.1)
        raise AssertionError(label)

    commands = json.loads(args.commands.read_text())
    assert set(commands) == {'worker', 'worker_fast'}
    for service, case in [('worker', 'startup'), ('worker_fast', 'count'), ('worker_fast', 'memory')]:
        command = commands[service]
        if isinstance(command, str):
            command = shlex.split(command)
        assert command[:4] == ['celery', '-A', 'celery_app', 'worker']
        assert '--max-memory-per-child=393216' in command
        # Same actual options, with only the external-boundary bootstrap changed.
        command = [sys.executable, '-m', 'celery', '-A', 'worker_environment'] + command[3:]
        with (root / f'{service}-{case}.log').open('w') as log:
            process = subprocess.Popen(command, cwd=project, env=dict(os.environ), stdout=log, stderr=subprocess.STDOUT)
            try:
                def stats():
                    assert process.poll() is None, 'Worker exited; inspect isolated log'
                    response = celery.control.inspect(timeout=1).stats()
                    if not response:
                        return None
                    assert len(response) == 1
                    return next(iter(response.values()))

                initial = wait_for(stats, 'Worker did not start', 60)
                assert initial['pid'] == process.pid
                assert initial['pool']['max-concurrency'] == 2
                assert initial['pool']['max-tasks-per-child'] == 50
                initial_pids = set(initial['pool']['processes'])
                assert len(initial_pids) == 2
                if service == 'worker':
                    print('LLM_REAL_PREFORK_STARTED concurrency=2 max_tasks=50', flush=True)
                    continue

                if case == 'count':
                    # Existing inactive-source no-op branch, real Admin/Redis.
                    # At least one child must retire by 100 completed tasks.
                    for number in range(100):
                        result = dispatch()
                        assert result.get(timeout=20) is None
                        result.forget()
                        if number == 48:
                            assert set(stats()['pool']['processes']) == initial_pids, 'Child recycled before 50 total tasks'
                    after_count = wait_for(lambda: (value if (value := stats()) and
                                           set(value['pool']['processes']) != initial_pids else None),
                                           'No child recycled after 100 completed tasks')
                    assert after_count['pid'] == process.pid
                    retired = initial_pids - set(after_count['pool']['processes'])
                    assert retired
                    wait_for(lambda: all(not Path(f'/proc/{pid}').exists() for pid in retired), 'Retired child not reaped')
                    print('COUNT_RECYCLE_REAL_ADMIN_TASKS completed=100 parent_survived=true', flush=True)
                    continue

                # Fresh pool: one task cannot reach the 50-task threshold.
                # This distinguishes RSS-triggered from count-triggered recycling.

                # An active RSS task crosses the real fetch Popen boundary. Hold
                # real memory there, with only DNS/socket/TLS simulated in exec.
                assert client.post(f'/admin/sources/{source_id}/toggle',
                                   data={'csrf_token': csrf('/admin/sources')}).status_code == 302
                (root / 'scenario.json').write_text(json.dumps({'routes': {'https://news.test.invalid/feed': {
                    'headers': {'Content-Type': 'application/rss+xml'},
                    'body': '<rss version="2.0"><channel><title>Fixture</title><link>https://news.test.invalid/</link>'
                            '<description>Empty synthetic feed</description></channel></rss>'}}}))
                (root / 'hold').touch()
                result = dispatch()
                wait_for(lambda: (root / 'held.json').exists(), 'Task never reached real fetch boundary')
                held = json.loads((root / 'held.json').read_text())
                assert held['rss_kib'] > 393216, 'Fixture did not actually cross RSS threshold'
                assert not result.ready(), 'Task finished before release'
                time.sleep(0.5)
                assert held['pid'] in stats()['pool']['processes'], 'Task was recycled while still running'
                (root / 'release').touch()
                value = result.get(timeout=30)
                assert value['new'] == 0 and value['found'] == 0 and not value['errors'], value
                result.forget()
                wait_for(lambda: (value if (value := stats()) and held['pid'] not in value['pool']['processes'] else None),
                         'Memory-heavy child was not recycled AFTER completion')
                wait_for(lambda: not Path(f'/proc/{held["pid"]}').exists(), 'Memory-heavy child not reaped')
                value = dispatch().get(timeout=30)
                assert value['new'] == 0 and not value['errors'], value
                response = client.get('/api/v1/news')
                assert response.status_code == 200 and response.json['total'] == 0
                assert stats()['pid'] == process.pid
                print(f'MEMORY_RECYCLE_AFTER_COMPLETION rss_kib={held["rss_kib"]} parent_survived=true next_task_ok=true', flush=True)
            finally:
                process.send_signal(signal.SIGTERM) if process.poll() is None else None
                try:
                    code = process.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise AssertionError('Warm shutdown failed; test process killed')
                assert code == 0, 'Worker did not shut down cleanly; inspect isolated log'
    before_task_publish.disconnect(observe_publish)
    print(f'WORKER_LIFECYCLE_OK artifacts={root}', flush=True)


if __name__ == '__main__':
    main()
