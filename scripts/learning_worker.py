"""Guarded learning-only worker startup and read-only runtime inspection.

Snapshot inspection proves only the supplied control protocol, never live readiness.
No model/crawl/email task is submitted. Do not print control replies or exceptions.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import sys


TASKS = {'app.crawlers.learning_tasks.learn', 'app.crawlers.learning_tasks.recover'}
# This entrypoint is deliberately not a generic command runner. Changing the
# learning worker contract requires matching Compose and protocol-gate review.
COMMAND = ['celery', '-A', 'celery_app', 'worker', '-l', 'info', '-Q', 'crawl_learn', '-c', '1',
           '-n', 'learn@%h', '--pool=prefork', '--prefetch-multiplier=1', '--max-tasks-per-child=50',
           '--max-memory-per-child=393216', '--soft-time-limit=180', '--time-limit=195']


def ready(data, node):
    try:
        if not isinstance(node, str) or not node.startswith('learn@') or len(node) > 255:
            return False
        if any(not isinstance(data[key], dict) or set(data[key]) != {node}
               for key in ('registered', 'active_queues', 'stats')):
            return False
        tasks = data['registered'][node]
        queues = data['active_queues'][node]
        stats = data['stats'][node]
        pool = stats['pool']
        return (isinstance(tasks, list) and all(isinstance(task, str) for task in tasks)
                and TASKS <= {task.split(' ', 1)[0] for task in tasks}
                and isinstance(queues, list) and len(queues) == 1
                and queues[0]['name'] == queues[0]['routing_key'] == 'crawl_learn'
                and queues[0]['exchange']['name'] == 'crawl_learn' and queues[0]['exchange']['type'] == 'direct'
                and pool['implementation'] == 'celery.concurrency.prefork:TaskPool'
                and type(pool['max-concurrency']) is int and pool['max-concurrency'] == 1
                and type(stats['prefetch_count']) is int and stats['prefetch_count'] == 1
                and isinstance(pool['processes'], list) and len(pool['processes']) == 1
                and type(pool['processes'][0]) is int and pool['processes'][0] > 0
                and pool['max-tasks-per-child'] == 50 and list(pool['timeouts']) == [180, 195])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


def no_constant(value):
    raise ValueError('Invalid constant')


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'INVALID_LEARNING_WORKER_ARGUMENTS\n')


def preflight():
    """Read-only local prerequisites, not model pricing or source approval."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text
    from app import create_app
    from app.extensions import db
    from app.crawlers._evidence import root

    app = create_app()
    if app.config.get('CRAWL_LEARNING_ENABLED') is not True:
        raise ValueError('Learning disabled')
    with root(app.config.get('CRAWL_EVIDENCE_DIR')) as folder:
        if not os.fstatvfs(folder).f_flag & os.ST_RDONLY:
            raise ValueError('Read-only evidence mount required')
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    heads = ScriptDirectory.from_config(config).get_heads()
    with app.app_context(), db.engine.connect() as connection:
        versions = list(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
    if len(heads) != 1 or versions != heads:
        raise ValueError('Current schema head required')
    return app


def main():
    parser = Arguments(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    check = sub.add_parser('check')
    check.add_argument('--snapshot', type=Path)
    check.add_argument('--node', default='learn@' + socket.gethostname())
    run = sub.add_parser('run')
    run.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    label = 'SNAPSHOT_LEARNING_WORKER' if getattr(args, 'snapshot', None) else 'LEARNING_WORKER'
    try:
        if args.mode == 'run':
            if args.command != COMMAND:
                raise ValueError('Unsupported worker command')
            preflight()
            os.execvp(args.command[0], args.command)
            return 0  # execvp does not return on a real successful handoff.
        if args.snapshot:
            with args.snapshot.open('rb') as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError('Snapshot too large')
            data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=no_constant)
        else:
            app = preflight()
            from celery_app import make_celery
            control = make_celery(app).control.inspect(destination=[args.node], timeout=2)
            data = {'registered': control.registered(), 'active_queues': control.active_queues(),
                    'stats': control.stats()}
        good = ready(data, args.node)
    except Exception:
        good = False
    print(label + ('_READY' if good else '_NOT_READY'))
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
