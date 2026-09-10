"""Disposable worker bootstrap; real app/tasks, injected OS boundaries only.

Not imported in production. Requires a guarded, private Linux test environment.
"""
import json
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import time

from sqlalchemy.engine import make_url

uri = make_url(os.environ['DATABASE_URL'])
assert uri.host == 'm0-mysql' and uri.database == 'fsource_m0_validation'
assert os.environ.get('FSI_DESTRUCTIVE_TESTS') == '1'
assert os.environ['CELERY_BROKER_URL'] == 'redis://worker-redis:6379/1'
assert os.environ['REDIS_URL'] == 'redis://worker-redis:6379/0'
ROOT = Path(os.environ['FSI_WORKER_STATE']).resolve()
SUPPORT = Path(__file__).resolve().parent

# Neither real news nor model/mail network access is permitted. Keep socket's
# class identity intact; parser/bootstrap imports may subclass it.
original_dns = socket.getaddrinfo
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
allowed = {}
for host, port in [('m0-mysql', 3306), ('worker-redis', 6379)]:
    ips = {row[4][0] for row in original_dns(host, port, type=socket.SOCK_STREAM)}
    allowed[(host, port)] = ips


def permitted(address):
    return isinstance(address, tuple) and any(
        address[1] == port and address[0] in ips | {host}
        for (host, port), ips in allowed.items())


def dns(host, port, *args, **kwargs):
    assert permitted((host, port)), 'Only isolated MySQL/Redis DNS permitted'
    return original_dns(host, port, *args, **kwargs)


def connect(sock, address):
    assert permitted(address), 'Only isolated MySQL/Redis sockets permitted'
    return original_connect(sock, address)


def connect_ex(sock, address):
    assert permitted(address), 'Only isolated MySQL/Redis sockets permitted'
    return original_connect_ex(sock, address)


socket.getaddrinfo = dns
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
original_popen = subprocess.Popen
retained = None


def popen(args, *positional, **kwargs):
    global retained
    if isinstance(args, (list, tuple)) and str(args[-1]).endswith('/_fetch_worker.py'):
        if (ROOT / 'hold').exists():
            try:
                fd = os.open(ROOT / 'claimed', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
                retained = bytearray(192 * 1024 * 1024)
                for index in range(0, len(retained), 4096):
                    retained[index] = 1
                data = {'pid': os.getpid(), 'rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
                (ROOT / 'held.tmp').write_text(json.dumps(data))
                (ROOT / 'held.tmp').rename(ROOT / 'held.json')
                end = time.monotonic() + 20
                while not (ROOT / 'release').exists():
                    if time.monotonic() >= end:
                        raise TimeoutError('Lifecycle test did not release the task')
                    time.sleep(0.02)
        args = [sys.executable, '-I', str(SUPPORT / 'fetch_network.py'), str(args[-1]),
                str(ROOT / 'scenario.json'), str(ROOT / 'network.jsonl')]
    return original_popen(args, *positional, **kwargs)


subprocess.Popen = popen
from celery_app import celery  # noqa: E402,F401 -- use the real application, no extra tasks
