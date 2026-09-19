"""Conservative model-exposure history, not independent validation or authority."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import unicodedata

from flask import current_app
from sqlalchemy import func, select

from app.models import CrawlLearningHistory, CrawlRepairSession, CrawlRepairAttempt, CrawlRepairRetry, LLMReservation, LLMUsageLog
from .quality import clean_document


FORMAT = 'learning-exposure.v1'
TEXT_VERSION = 'visible-text.v1'
MAX_RECORDS = 4096
_HASH = re.compile(r'[0-9a-f]{64}')
_PAGE_FIELDS = {'requested_url_hash', 'document_url_hash', 'snapshot_id', 'response_bytes', 'fetched_at',
                'text_hash', 'text_version'}


@dataclass(frozen=True)
class Coverage:
    state: str
    sessions: int
    exposures: int


def _limit():
    value = current_app.config.get('CRAWL_LEARNING_HISTORY_SCAN_LIMIT', MAX_RECORDS)
    if type(value) not in (str, int):
        raise ValueError('Invalid learning history limit')
    limit = int(value)
    if not 1 <= limit <= MAX_RECORDS:
        raise ValueError('Invalid learning history limit')
    return limit


def _hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _digest(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > 16384:
        raise ValueError('Learning history document too large')
    return hashlib.sha256(data).hexdigest()


def session_hash(item):
    return _digest({'format': FORMAT, 'id': item.id, 'sequence': item.history_sequence,
        'source_id': item.source_id, 'base_version_id': item.base_version_id, 'capture_id': item.capture_id,
        'evidence': item.evidence, 'protocol_version': item.protocol_version, 'created_by_id': item.created_by_id,
        'max_rounds': item.max_rounds, 'cost_limit': format(item.cost_limit, '.6f'),
        # MySQL DATETIME currently stores seconds, SQLite also stores microseconds.
        'created_at': item.created_at.replace(microsecond=0).isoformat(),
        'deadline_at': item.deadline_at.replace(microsecond=0).isoformat()})


def exposure_hash(attempt, parent_hash):
    return _digest({'format': FORMAT, 'id': attempt.id, 'session_id': attempt.session_id,
        'number': attempt.number, 'sequence': attempt.exposure_sequence, 'input_hash': parent_hash,
        'prompt_hash': attempt.prompt_hash, 'documents': attempt.exposure})


def retry_hash(record, parent_hash):
    return _digest({'format': 'learning-retry.v1', 'id': record.id, 'session_id': record.session_id,
        'input_hash': parent_hash, 'number': record.number, 'after_round': record.after_round,
        'requested_by_id': record.requested_by_id, 'requested_at': record.requested_at.isoformat(),
        'note': record.note})


def documents(pages):
    result = []
    for page in pages:
        root = clean_document(page.response.body)
        paragraphs = [p.get_text(' ', strip=True) for p in root.select('p')]
        visible = '\n'.join(paragraphs) if paragraphs else root.get_text(' ', strip=True)
        visible = ' '.join(unicodedata.normalize('NFKC', visible).casefold().split())
        result.append({'requested_url_hash': hashlib.sha256(page.url.encode()).hexdigest(),
            'document_url_hash': hashlib.sha256(page.response.document_url.encode()).hexdigest(),
            'snapshot_id': page.response.observation.snapshot_id,
            'response_bytes': len(page.response.body), 'fetched_at': page.response.observation.fetched_at.isoformat(),
            'text_hash': hashlib.sha256(visible.encode()).hexdigest(), 'text_version': TEXT_VERSION})
    return result


def initialize(session):
    """Only a genuinely empty workflow can bootstrap; caller holds the budget gate."""
    marker = session.get(CrawlLearningHistory, 1)
    if marker is None:
        if session.scalar(select(func.count()).select_from(CrawlLearningHistory)):
            raise ValueError('Learning history marker unavailable')
        sessions = session.scalar(select(func.count()).select_from(CrawlRepairSession))
        exposures = session.scalar(select(func.count()).select_from(CrawlRepairAttempt))
        prior_money = session.scalar(select(LLMReservation.id).where(LLMReservation.task_type == 'crawl_schema').limit(1))
        prior_usage = session.scalar(select(LLMUsageLog.id).where(LLMUsageLog.task_type == 'crawl_schema').limit(1))
        if sessions or exposures or prior_money or prior_usage:
            raise ValueError('Learning history marker unavailable')
        marker = CrawlLearningHistory(id=1, session_generation=0, exposure_generation=0, history_complete=True)
        session.add(marker)
        session.flush()
    return marker


def record_session(session, item):
    marker = initialize(session)
    if max(marker.session_generation, marker.exposure_generation) >= _limit():
        raise ValueError('Learning history capacity reached')
    marker.session_generation += 1
    item.history_sequence = marker.session_generation
    session.add(item)
    session.flush()
    item.input_hash = session_hash(item)


def record_exposure(session, item, attempt):
    marker = session.get(CrawlLearningHistory, 1)
    if marker is None:
        raise ValueError('Learning history marker unavailable')
    if marker.exposure_generation >= _limit():
        raise ValueError('Learning history capacity reached')
    marker.exposure_generation += 1
    attempt.exposure_sequence = marker.exposure_generation
    attempt.exposure_hash = exposure_hash(attempt, item.input_hash)
    session.add(attempt)


def inspect(session):
    marker = session.get(CrawlLearningHistory, 1)
    sessions = session.scalar(select(func.count()).select_from(CrawlRepairSession))
    exposures = session.scalar(select(func.count()).select_from(CrawlRepairAttempt))
    if marker is None:
        return Coverage('unavailable' if sessions or exposures else 'unconfigured', sessions, exposures)
    if session.scalar(select(func.count()).select_from(CrawlLearningHistory)) != 1:
        return Coverage('unavailable', sessions, exposures)
    if not marker.history_complete:
        return Coverage('incomplete', sessions, exposures)
    unavailable = Coverage('unavailable', sessions, exposures)
    try:
        limit = _limit()
    except (ValueError, TypeError, OverflowError):
        return unavailable
    retries = session.scalar(select(func.count()).select_from(CrawlRepairRetry))
    if (sessions > limit or exposures > limit or retries > limit
            or marker.session_generation != sessions or marker.exposure_generation != exposures):
        return unavailable
    parents = session.scalars(select(CrawlRepairSession).order_by(CrawlRepairSession.history_sequence)
                              .limit(limit + 1).execution_options(populate_existing=True)).all()
    attempts = session.scalars(select(CrawlRepairAttempt).order_by(CrawlRepairAttempt.exposure_sequence)
                               .limit(limit + 1).execution_options(populate_existing=True)).all()
    if ([p.history_sequence for p in parents] != list(range(1, sessions + 1))
            or [a.exposure_sequence for a in attempts] != list(range(1, exposures + 1))):
        return unavailable
    rounds = {p.id: [] for p in parents}
    for attempt in attempts:
        if attempt.session_id not in rounds:
            return unavailable
        rounds[attempt.session_id].append(attempt.number)
    if any(type(p.rounds) is not int or not 0 <= p.rounds <= 3
           or rounds[p.id] != list(range(1, p.rounds + 1)) for p in parents):
        return unavailable
    try:
        if any(not _hash(p.input_hash) or p.input_hash != session_hash(p) for p in parents):
            return unavailable
        inputs = {p.id: p.input_hash for p in parents}
        records = session.scalars(select(CrawlRepairRetry).order_by(CrawlRepairRetry.number)
                                  .limit(limit + 1).execution_options(populate_existing=True)).all()
        by_session = {p.id: [] for p in parents}
        for record in records:
            if (record.session_id not in inputs or type(record.after_round) is not int
                    or not 0 <= record.after_round < 3 or not isinstance(record.note, str)
                    or not 1 <= len(record.note.strip()) <= 300
                    or record.document_hash != retry_hash(record, inputs[record.session_id])):
                return unavailable
            by_session[record.session_id].append(record)
        for parent in parents:
            rows = by_session[parent.id]
            if (type(parent.retry_count) is not int or not 0 <= parent.retry_count <= 3
                    or [r.number for r in rows] != list(range(1, parent.retry_count + 1))
                    or len({r.after_round for r in rows}) != len(rows)
                    or any(r.after_round > parent.rounds or r.requested_at < parent.created_at
                           or r.requested_at >= parent.deadline_at for r in rows)
                    or (parent.state in ('blocked', 'exhausted', 'cancelled') and parent.cooldown_until is None)):
                return unavailable
        if any(not _hash(a.prompt_hash) or not _hash(a.exposure_hash) or display_documents(a) is None
               or a.exposure_hash != exposure_hash(a, inputs[a.session_id]) for a in attempts):
            return unavailable
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        return unavailable
    return Coverage('tracked', sessions, exposures)


def require(session):
    if inspect(session).state != 'tracked':
        raise ValueError('Learning exposure history unavailable')
    from .validation import require_history
    require_history(session)


def display_documents(attempt):
    """Never render arbitrary corrupted DB content as an exposure audit."""
    value = attempt.exposure
    if not isinstance(value, list) or not 1 <= len(value) <= 6:
        return None
    for page in value:
        if (not isinstance(page, dict) or set(page) != _PAGE_FIELDS
                or any(not _hash(page[name]) for name in ('requested_url_hash', 'document_url_hash', 'text_hash'))
                or page['text_version'] != TEXT_VERSION or not isinstance(page['snapshot_id'], str)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', page['snapshot_id'])
                or type(page['response_bytes']) is not int or not 0 <= page['response_bytes'] <= 512 * 1024
                or not isinstance(page['fetched_at'], str) or len(page['fetched_at']) > 40):
            return None
        try:
            if datetime.fromisoformat(page['fetched_at']).tzinfo is None:
                return None
        except ValueError:
            return None
    if sum(p['response_bytes'] for p in value) > 2 * 1024 * 1024:
        return None
    return value
