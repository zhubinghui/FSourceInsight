"""Test helpers for claimed crawl runs; production code never imports this module."""
from datetime import timedelta


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, **delta):
        self.value += timedelta(**delta)


def claimed(source_id):
    """Claim a source now, as the dispatcher would, regardless of its due time."""
    from app.crawlers import runs, schedule
    runs.ensure_states(schedule.now())
    claim = runs.claim(source_id, due_only=False)
    assert claim is not None, 'source is disabled or already has a live claim'
    return claim
