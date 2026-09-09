"""Offline deployment contract checks; no Docker daemon or .env resolution."""
import json
from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('caddy', [False, True])
def test_production_compose_does_not_inherit_dev_endpoints(caddy):
    docker = shutil.which('docker')
    if not docker:
        pytest.skip('Docker Compose CLI required for offline merge validation')
    command = [docker, 'compose', '--env-file', '/dev/null', '-f', 'docker-compose.yml', '-f', 'docker-compose.prod.yml']
    if caddy:
        command += ['-f', 'docker-compose.caddy.yml']
    command += ['config', '--no-env-resolution', '--no-interpolate', '--format', 'json']
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30,
                            env={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']})
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)['services']
    for name in ['mysql', 'redis']:
        assert not services[name].get('ports')
    for name in ['web', 'worker', 'worker_fast', 'beat']:
        assert not services[name].get('volumes')
    if caddy:
        assert services['web']['ports'] == [{'mode': 'ingress', 'host_ip': '127.0.0.1', 'target': 8000, 'published': '8800', 'protocol': 'tcp'}]
        assert services['nginx']['profiles'] == ['nginx-disabled']
    else:
        assert not services['web'].get('ports')
        assert {port['published'] for port in services['nginx']['ports']} == {'80', '443'}


@pytest.mark.parametrize('caddy', [False, True])
def test_opt_in_evidence_is_private_persistent_and_web_only(caddy):
    docker = shutil.which('docker')
    if not docker:
        pytest.skip('Docker Compose CLI required for offline merge validation')
    command = [docker, 'compose', '--env-file', '/dev/null', '-f', 'docker-compose.yml', '-f', 'docker-compose.prod.yml']
    if caddy:
        command += ['-f', 'docker-compose.caddy.yml']
    command += ['-f', 'docker-compose.evidence.yml', 'config', '--no-env-resolution', '--no-interpolate', '--format', 'json']
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30,
                            env={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    services = data['services']
    environment = services['web']['environment']
    if isinstance(environment, list):
        environment = dict(item.split('=', 1) for item in environment)
    assert environment['CRAWL_EVIDENCE_DIR'] == '/var/lib/fsource-evidence'
    mounts = services['web']['volumes']
    assert len(mounts) == 1
    assert {key: mounts[0][key] for key in ['type', 'source', 'target']} == {
        'type': 'volume', 'source': 'crawl_evidence_data', 'target': '/var/lib/fsource-evidence'}
    assert data['volumes']['crawl_evidence_data']['external'] is True
    assert data['volumes']['crawl_evidence_data']['name'] == 'fsourceinsight_crawl_evidence_data'
    for name in ['worker', 'worker_fast', 'beat']:
        assert not services[name].get('volumes')
        environment = services[name].get('environment', {})
        if isinstance(environment, list):
            environment = dict(item.split('=', 1) for item in environment)
        assert 'CRAWL_EVIDENCE_DIR' not in environment
    for name in ['mysql', 'redis']:
        assert not services[name].get('ports')
    if caddy:
        assert services['web']['ports'][0]['host_ip'] == '127.0.0.1'
        assert services['web']['ports'][0]['published'] == '8800'
    else:
        assert not services['web'].get('ports')


def test_docker_build_context_is_explicit_allowlist():
    rules = [line.strip() for line in (ROOT / '.dockerignore').read_text().splitlines()
             if line.strip() and not line.startswith('#')]
    assert rules[0] == '**'
    # Adding a new allowed tree requires explicit review of this contract.
    allowed = {'!app/', '!app/**', '!migrations/', '!migrations/**',
               '!requirements/', '!requirements/base.txt', '!requirements/prod.txt',
               '!scripts/', '!scripts/*.py', '!celery_app.py', '!wsgi.py'}
    assert {rule for rule in rules if rule.startswith('!')} == allowed
    assert rules.index('**/.env*') > rules.index('!app/**')
    assert '**/*.sql*' in rules
    for name in ['web', 'worker']:
        dockerfile = (ROOT / 'docker' / f'Dockerfile.{name}').read_text()
        assert 'COPY . .' not in dockerfile
        assert 'COPY app/ app/' in dockerfile
        assert 'COPY scripts/*.py scripts/' in dockerfile
