"""Permanent fingerprint-only sampling history; not validation or permission."""
import hashlib
import json
import re
from datetime import datetime


_HEX = re.compile(r'[0-9a-f]{64}')
_STATUSES = {'ready', 'no_change', 'partial', 'degraded', 'blocked', 'failed', 'inconclusive'}
_FIELDS = {'format', 'purpose', 'source_id', 'version_id', 'preview_report_id', 'generation', 'source_generation',
           'source_fingerprint', 'recipe_hash', 'engine_version', 'source_policy', 'capture_id', 'result_status',
           'completion_status', 'documents', 'sequence', 'fetch_policy_hash', 'quality_profile_hash'}


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2 ** 31 - 1


def _hash(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def checked_document(record, source_id):
    """Validate before displaying/consuming stored metadata; hashes are not authority."""
    value = record.document
    if not isinstance(value, dict) or set(value) != _FIELDS or fingerprint(value) != record.document_hash:
        raise ValueError('Invalid capture manifest')
    if (value['format'] != 'crawl-capture.v1' or value['purpose'] != 'preview'
            or value['source_id'] != source_id or value['version_id'] != record.version_id
            or value['preview_report_id'] != record.preview_report_id or value['sequence'] != record.sequence):
        raise ValueError('Invalid capture binding')
    for field in ('source_id', 'version_id', 'preview_report_id', 'sequence'):
        if not _integer(value[field], 1):
            raise ValueError('Invalid capture identity')
    if not all(_integer(value[key]) for key in ('generation', 'source_generation')):
        raise ValueError('Invalid capture generation')
    if not all(_hash(value[key]) for key in ('source_fingerprint', 'recipe_hash', 'fetch_policy_hash', 'quality_profile_hash')):
        raise ValueError('Invalid capture input')
    if (type(value['engine_version']) is not str or not re.fullmatch(r'[a-z0-9._-]{1,40}', value['engine_version'])
            or type(value['capture_id']) is not str or not re.fullmatch(r'[0-9a-f]{32}', value['capture_id'])
            or type(value['result_status']) is not str or value['result_status'] not in _STATUSES
            or type(value['completion_status']) is not str or value['completion_status'] not in _STATUSES | {'stale'}):
        raise ValueError('Invalid capture result')
    policy = value['source_policy']
    if policy is not None and (not isinstance(policy, dict) or set(policy) != {'id', 'hash'}
                              or not _integer(policy['id'], 1) or not _hash(policy['hash'])):
        raise ValueError('Invalid capture policy')
    pages = value['documents']
    if not isinstance(pages, list) or len(pages) > 6:
        raise ValueError('Invalid capture pages')
    for page in pages:
        if (not isinstance(page, dict) or set(page) != {'requested_url_hash', 'document_url_hash', 'snapshot_id', 'response_bytes', 'fetched_at'}
                or not _hash(page['requested_url_hash']) or not _hash(page['document_url_hash'])
                or type(page['snapshot_id']) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', page['snapshot_id'])
                or not _integer(page['response_bytes']) or page['response_bytes'] > 512 * 1024
                or type(page['fetched_at']) is not str or len(page['fetched_at']) > 40
                or datetime.fromisoformat(page['fetched_at']).tzinfo is None):
            raise ValueError('Invalid captured page')
    if sum(page['response_bytes'] for page in pages) > 2 * 1024 * 1024:
        raise ValueError('Invalid capture size')
    return value


def fingerprint(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    if len(encoded) > 8192:
        raise ValueError('Capture manifest too large')
    return hashlib.sha256(encoded).hexdigest()


def history_state(profile):
    from sqlalchemy import and_, func
    from app.extensions import db
    from app.models.crawl_schema import CrawlCaptureManifest, CrawlPreviewReport, CrawlSchemaVersion

    if profile is None:
        return 'unconfigured'
    count, first, last = (db.session.query(func.count(CrawlCaptureManifest.id), func.min(CrawlCaptureManifest.sequence),
                                         func.max(CrawlCaptureManifest.sequence))
                          .filter(CrawlCaptureManifest.profile_id == profile.id).one())
    marker = profile.capture_generation
    if (type(marker) is not int or not 0 <= marker < 2 ** 31 - 1 or count != marker
            or count and (first != 1 or last != marker)):
        return 'unavailable'
    if profile.capture_history_complete:
        missing = (db.session.query(CrawlPreviewReport.id).join(CrawlSchemaVersion)
                   .outerjoin(CrawlCaptureManifest, and_(CrawlCaptureManifest.preview_report_id == CrawlPreviewReport.id,
                              CrawlCaptureManifest.profile_id == profile.id,
                              CrawlCaptureManifest.version_id == CrawlPreviewReport.version_id))
                   .filter(CrawlSchemaVersion.profile_id == profile.id, CrawlCaptureManifest.id.is_(None)).first())
        if missing:
            return 'unavailable'
        return 'tracked'
    return 'incomplete'


def reference_id(report, profile):
    from app.models.crawl_schema import CrawlCaptureManifest

    reference = report.report.get('capture_manifest')
    if (not isinstance(reference, dict) or set(reference) != {'id', 'hash'}
            or not _integer(reference['id'], 1) or not _hash(reference['hash'])):
        return None
    record = CrawlCaptureManifest.query.filter_by(id=reference['id'], profile_id=profile.id,
                version_id=report.version_id, preview_report_id=report.id, document_hash=reference['hash']).one_or_none()
    if record is None:
        return None
    try:
        value = checked_document(record, profile.source_id)
    except (ValueError, TypeError, RecursionError):
        return None
    if (value['capture_id'] != report.report.get('capture_id') or value['recipe_hash'] != report.recipe_hash
            or value['source_fingerprint'] != report.source_fingerprint or value['generation'] != report.generation):
        return None
    return record.id


def document(source_id, source_generation, report, snapshots):
    return {
        'format': 'crawl-capture.v1', 'purpose': 'preview',
        'source_id': source_id, 'version_id': report.version_id,
        'preview_report_id': report.id,
        'generation': report.generation, 'source_generation': source_generation,
        'source_fingerprint': report.source_fingerprint,
        'recipe_hash': report.recipe_hash, 'engine_version': report.engine_version,
        'source_policy': report.report['source_policy'],
        'fetch_policy_hash': fingerprint(report.report['fetch_policy']),
        'quality_profile_hash': fingerprint(report.report['quality_profile']),
        'capture_id': report.report['capture_id'],
        'result_status': report.report['result_status'], 'completion_status': report.status,
        'documents': [{
            'requested_url_hash': hashlib.sha256(page.url.encode()).hexdigest(),
            'document_url_hash': hashlib.sha256(page.response.document_url.encode()).hexdigest(),
            'snapshot_id': page.response.observation.snapshot_id,
            'response_bytes': len(page.response.body),
            'fetched_at': page.response.observation.fetched_at.isoformat(),
        } for page in snapshots],
    }
