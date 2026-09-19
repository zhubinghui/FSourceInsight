"""Message identity is a fence, never source permission or a new paid lease."""
from datetime import timedelta
import hashlib
import json
import re

from flask import current_app

from app.llm import budget
from app.models import CrawlRepairSession

VERSION = 'learning-delivery.v1'


def key(item):
    if (item.dispatch_due_at is None or not isinstance(item.input_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', item.input_hash)
            or type(item.rounds) is not int or not 0 <= item.rounds < 3
            or type(item.retry_count) is not int or not 0 <= item.retry_count <= 3):
        return None
    body = {'format': VERSION, 'session': item.id, 'input_hash': item.input_hash,
            'after_round': item.rounds, 'after_retry': item.retry_count}
    return 'ld1:' + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def matches(item, value):
    return isinstance(value, str) and value == key(item)


def publish(identity):
    from celery_app import celery
    from . import learning
    try:
        with budget.transaction() as session:
            item = session.get(CrawlRepairSession, identity)
            if item is None or item.state != 'queued':
                return
            learning.enabled()
            timestamp = budget.now()
            if timestamp >= item.deadline_at:
                learning.stop(session, item, 'blocked', 'Deadline expired; uncertain work is not retried')
                return
            token = key(item)
            if token is None:
                learning.stop(session, item, 'blocked', 'Learning delivery unavailable')
                return
            if item.dispatch_due_at > timestamp:
                return
            # COMMIT before broker I/O. Lost ACK/publication consumes this interval too.
            item.dispatch_due_at = timestamp.replace(microsecond=0) + timedelta(seconds=31)
        celery.send_task('app.crawlers.learning_tasks.learn', args=[identity, token], queue='crawl_learn')
    except Exception:
        current_app.logger.warning('crawl_learning_dispatch_unavailable')
