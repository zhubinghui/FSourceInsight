"""One next-due rule for every source: frequency plus a daily local anchor (spec §5.4).

Pure functions apart from now() and anchor_settings(); times are naive UTC.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

RETRY = frozenset({'timeout', 'network_error', 'server_error', 'rate_limited', 'database_error',
                   'fetch_closed', 'transport_unavailable', 'budget_exceeded'})
BLOCKED = frozenset({'forbidden', 'robots_denied', 'robots_unavailable', 'unsafe_url', 'tls_error',
                     'login_required', 'paywall', 'captcha', 'http_error', 'redirect_limit',
                     'schema_stale', 'policy_unavailable', 'invalid_schema'})
LEASE = timedelta(minutes=15)
ANCHOR_GAP = timedelta(minutes=30)
COOLDOWN = timedelta(hours=24)
MIN_FREQUENCY = 15
EXTRACTION_ATTENTION = 3
DEFAULT_HOUR, DEFAULT_ZONE = 1, 'Europe/Paris'


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def kind(error_code):
    if error_code is None:
        return 'ok'
    if error_code in RETRY:
        return 'retry'
    if error_code in BLOCKED:
        return 'blocked'
    return 'extraction'


def anchor_settings(session):
    from app.models.setting import SystemSetting
    values = dict(session.execute(select(SystemSetting.key, SystemSetting.value).where(
        SystemSetting.key.in_(('crawl_daily_hour', 'crawl_timezone')))).all())
    try:
        hour = int(values.get('crawl_daily_hour', DEFAULT_HOUR))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    zone = values.get('crawl_timezone') or DEFAULT_ZONE
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = DEFAULT_ZONE
    return (hour if 0 <= hour <= 23 else DEFAULT_HOUR), zone


def anchor_after(moment, hour, zone):
    """First local hour:00 strictly after naive-UTC moment.

    fold=0 picks the first of a repeated autumn hour; a spring-gap hour takes the
    pre-transition offset, which is exactly the first instant after the gap.
    """
    tz = ZoneInfo(zone)
    day = moment.replace(tzinfo=timezone.utc).astimezone(tz).date()
    for offset in range(3):
        local = datetime.combine(day + timedelta(days=offset), time(hour), tz)
        candidate = local.astimezone(timezone.utc).replace(tzinfo=None)
        if candidate > moment:
            return candidate
    raise AssertionError('an anchor exists within three local days')


def next_due(*, error_code, started, finished, frequency, failures, retry_after, hour, zone):
    period = timedelta(minutes=max(frequency or 0, MIN_FREQUENCY))
    category = kind(error_code)
    if category == 'retry':
        if retry_after:
            return finished + timedelta(seconds=min(retry_after, 86400))
        return finished + min(period, timedelta(minutes=15) * 2 ** min(max(failures - 1, 0), 16))
    if category == 'blocked':
        return finished + COOLDOWN
    return min(started + period, anchor_after(started + ANCHOR_GAP, hour, zone))
