"""The single next-due rule (spec §5.4), including Paris DST anchors."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.crawlers import schedule

PARIS = 'Europe/Paris'
START = datetime(2026, 9, 25, 10, 0)


def due(error_code=None, *, started=START, finished=None, frequency=360, failures=1, retry_after=None, hour=1, zone=PARIS):
    return schedule.next_due(error_code=error_code, started=started, finished=finished or started,
                             frequency=frequency, failures=failures, retry_after=retry_after, hour=hour, zone=zone)


def test_success_uses_the_earlier_of_frequency_and_the_daily_anchor():
    # 01:00 Paris is 23:00 UTC in September.
    assert due(started=datetime(2026, 9, 25, 18, 0), frequency=720) == datetime(2026, 9, 25, 23, 0)
    assert due(started=START, frequency=360) == datetime(2026, 9, 25, 16, 0)


def test_a_run_just_before_the_anchor_does_not_run_again_at_the_anchor():
    assert due(started=datetime(2026, 9, 25, 22, 40), frequency=1440) == datetime(2026, 9, 26, 22, 40)


def test_autumn_repeated_local_hour_is_a_single_instant():
    # 2026-10-25: Paris 02:00-03:00 happens twice; the first one is 00:00 UTC.
    assert due(started=datetime(2026, 10, 24, 12, 0), frequency=10080, hour=2) == datetime(2026, 10, 25, 0, 0)
    assert due(started=datetime(2026, 10, 25, 0, 0), frequency=10080, hour=2) == datetime(2026, 10, 26, 1, 0)


def test_spring_gap_hour_moves_to_the_first_instant_after_the_gap():
    # 2026-03-29: Paris jumps from 02:00 CET to 03:00 CEST at 01:00 UTC.
    assert due(started=datetime(2026, 3, 28, 12, 0), frequency=10080, hour=2) == datetime(2026, 3, 29, 1, 0)


@pytest.mark.parametrize('failures, wait', [(1, 15), (2, 30), (3, 60), (5, 240), (9, 360), (60, 360)])
def test_retryable_failures_back_off_up_to_the_source_frequency(failures, wait):
    finished = START + timedelta(minutes=1)
    assert due('timeout', finished=finished, failures=failures) == finished + timedelta(minutes=wait)


def test_retry_after_is_honoured_and_capped_at_a_day():
    assert due('rate_limited', retry_after=600) == START + timedelta(minutes=10)
    assert due('rate_limited', retry_after=10 ** 9) == START + timedelta(days=1)


@pytest.mark.parametrize('code', ['forbidden', 'robots_denied', 'robots_unavailable', 'unsafe_url', 'tls_error',
                                  'http_error', 'schema_stale', 'policy_unavailable', 'invalid_schema'])
def test_access_failures_cool_down_for_a_day(code):
    assert schedule.kind(code) == 'blocked'
    finished = START + timedelta(minutes=2)
    assert due(code, finished=finished) == finished + timedelta(days=1)


@pytest.mark.parametrize('code', ['empty_extraction', 'low_quality', 'missing_fields', 'crawler_error',
                                  'no_evidence', 'invalid_article'])
def test_extraction_failures_keep_the_normal_schedule(code):
    assert schedule.kind(code) == 'extraction'
    assert due(code, finished=START + timedelta(minutes=5)) == START + timedelta(minutes=360)


@pytest.mark.parametrize('frequency', [0, -5, None, 3])
def test_a_missing_or_non_positive_frequency_never_busy_loops(frequency):
    assert due(frequency=frequency) == START + timedelta(minutes=15)


@pytest.mark.parametrize('hour, zone, expected', [
    ('7', 'Europe/Paris', (7, 'Europe/Paris')),
    ('25', 'Mars/Olympus', (1, 'Europe/Paris')),
    ('x', '', (1, 'Europe/Paris')),
])
def test_anchor_settings_fall_back_to_the_default(db, hour, zone, expected):
    from app.models.setting import SystemSetting
    SystemSetting.set('crawl_daily_hour', hour)
    SystemSetting.set('crawl_timezone', zone)
    db.session.commit()
    with Session(db.engine) as session:
        assert schedule.anchor_settings(session) == expected
