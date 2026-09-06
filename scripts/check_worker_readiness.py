"""Read-only Celery deployment gate; never queues crawl, LLM or email tasks."""
import argparse
import json
from pathlib import Path
import sys
import time


REQUIRED_TASKS = {
    'app.crawlers.tasks.crawl_source',
    'app.llm.tasks.process_article_llm',
    'app.email.tasks.send_daily_digest',
}


def workers_ready(registrations, expected_workers=2):
    if not isinstance(registrations, dict) or len(registrations) != expected_workers:
        return False
    # Celery appends task metadata, e.g. "task.name [rate_limit=10/m]".
    # Compare normalized names, not a permissive prefix or the decorated string.
    return all(isinstance(tasks, list)
               and all(isinstance(task, str) for task in tasks)
               and REQUIRED_TASKS.issubset({task.split(' ', 1)[0] for task in tasks})
               for tasks in registrations.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, help='Offline fixture JSON (does not contact workers)')
    parser.add_argument('--expected-workers', type=int, default=2)
    args = parser.parse_args()
    if args.snapshot:
        ready = workers_ready(json.loads(args.snapshot.read_text()), args.expected_workers)
        print('SNAPSHOT_READY' if ready else 'SNAPSHOT_NOT_READY')
        return 0 if ready else 1

    if __file__ != '<stdin>':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from celery_app import celery
    for _ in range(10):
        replies = celery.control.inspect(timeout=3).registered()
        if workers_ready(replies, args.expected_workers):
            print('LIVE_WORKERS_READY')
            return 0
        time.sleep(2)
    print('LIVE_WORKERS_NOT_READY', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
