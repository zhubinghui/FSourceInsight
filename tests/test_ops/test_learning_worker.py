"""Public operations boundaries: real Compose merge and learning worker CLI."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def compose(caddy=False, enabled='0', profile=True):
    docker = shutil.which('docker')
    if not docker:
        pytest.skip('Compose CLI required for offline merge validation')
    command = [docker, 'compose', '--env-file', '/dev/null', '-f', 'docker-compose.yml',
               '-f', 'docker-compose.prod.yml']
    if caddy:
        command += ['-f', 'docker-compose.caddy.yml']
    command += ['-f', 'docker-compose.evidence.yml', '-f', 'docker-compose.learning.yml']
    if profile:
        command += ['--profile', 'crawl-learning']
    result = subprocess.run(command + ['config', '--no-env-resolution', '--format', 'json'], cwd=ROOT,
        env={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME'], 'CRAWL_LEARNING_ENABLED': enabled},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('caddy', [False, True])
@pytest.mark.parametrize('enabled', ['0', '1'])
def test_optional_worker_has_one_private_queue_readonly_evidence_and_bounded_resources(caddy, enabled):
    data = compose(caddy, enabled)
    services = data['services']
    worker = services['worker_learn']
    assert worker['profiles'] == ['crawl-learning']
    assert not worker.get('ports')
    assert worker['entrypoint'] == ['python', 'scripts/learning_worker.py', 'run']
    assert worker['command'] == ['celery', '-A', 'celery_app', 'worker', '-l', 'info',
        '-Q', 'crawl_learn', '-c', '1', '-n', 'learn@%h', '--pool=prefork', '--prefetch-multiplier=1',
        '--max-tasks-per-child=50', '--max-memory-per-child=393216', '--soft-time-limit=180', '--time-limit=195']
    assert worker['read_only'] is True and worker['init'] is True
    assert worker['cap_drop'] == ['ALL']
    assert worker['security_opt'] == ['no-new-privileges:true']
    assert worker['pids_limit'] == 64
    limits = worker['deploy']['resources']['limits']
    assert float(limits['cpus']) == 1
    assert int(limits['memory']) == 1073741824 and limits['pids'] == 64
    assert worker['tmpfs'] == ['/tmp:size=64m,mode=1777']
    assert worker['stop_grace_period'] == '3m30s'
    assert worker['healthcheck']['test'] == ['CMD', 'python', 'scripts/learning_worker.py', 'check']
    assert worker['healthcheck']['timeout'] == '20s'
    mounts = worker['volumes']
    assert len(mounts) == 1
    assert mounts[0] == {'type': 'volume', 'source': 'crawl_evidence_data',
                         'target': '/var/lib/fsource-evidence', 'read_only': True, 'volume': {'nocopy': True}}
    assert services['web']['volumes'][0]['source'] == mounts[0]['source']
    assert not services['web']['volumes'][0].get('read_only')
    assert data['volumes']['crawl_evidence_data']['external'] is True
    for name in ('web', 'beat', 'worker_learn'):
        assert services[name]['environment']['CRAWL_LEARNING_ENABLED'] == enabled
    for name in ('worker', 'worker_fast', 'beat'):
        assert not services[name].get('volumes')
    for name, queue in [('worker', 'llm'), ('worker_fast', 'crawl,email')]:
        args = services[name]['command']
        assert args[args.index('-Q') + 1] == queue
        assert args[args.index('-c') + 1] == '2'
    assert not services['mysql'].get('ports') and not services['redis'].get('ports')
    assert worker['environment']['PYTHONDONTWRITEBYTECODE'] == '1'
    assert worker['environment']['LOG_FILE'].startswith('/tmp/')


def test_adding_learning_overlay_without_profile_does_not_start_a_consumer():
    assert 'worker_learn' not in compose(profile=False)['services']
