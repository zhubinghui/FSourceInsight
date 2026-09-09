"""Bounded admin report data. No raw snapshots or approval authority are retained."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json

from .fetcher import FetchPolicy
from .quality import QualityProfile


REPORT_VERSION = 'admin-preview.v1'


def source_fingerprint(source):
    # Operational timestamps/name/frequency do not change extraction inputs.
    values = {name: getattr(source, name) for name in (
        'id', 'url', 'feed_url', 'feed_type', 'crawler_class', 'slug', 'is_active')}
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preview_policy(hosts, kind):
    if len(hosts) > 4096 or kind not in {'news', 'bulletin'}:
        raise ValueError('Invalid preview policy')
    policy = FetchPolicy(
        allowed_hosts=tuple(host.strip() for host in hosts.splitlines() if host.strip()),
        max_seconds=20, max_requests=6, max_redirects=3,
        max_response_bytes=512 * 1024, max_wire_bytes=512 * 1024,
        max_total_bytes=2 * 1024 * 1024, max_total_wire_bytes=2 * 1024 * 1024,
    )
    quality = QualityProfile(min_content_chars=80, min_paragraphs=1) if kind == 'bulletin' else QualityProfile()
    return policy, quality


def report_data(result, policy, quality):
    samples = [{
        'title': article.title, 'url': article.url,
        'content_excerpt': (article.content or '')[:1000],
        'excerpt_truncated': len(article.content or '') > 1000,
        'content_level': article.content_level, 'source_language': article.source_language,
        'published_at': article.published_at.isoformat() if article.published_at else None,
        'provenance': [asdict(value) for value in article.provenance],
    } for article in result.articles[:5]]
    value = {
        'format': REPORT_VERSION, 'result_status': result.status,
        'fetch_policy': asdict(policy), 'quality_profile': asdict(quality),
        'quality': asdict(result.quality), 'content_levels': dict(Counter(a.content_level for a in result.articles)),
        'errors': [{'stage': error.stage, 'code': error.code} for error in result.errors],
        'samples': samples, 'samples_truncated': len(result.articles) > len(samples),
        'raw_snapshots_retained': False,
        'documents': [{
            'snapshot_id': page.response.observation.snapshot_id,
            'document_url_hash': hashlib.sha256(page.response.document_url.encode()).hexdigest(),
            'response_bytes': len(page.response.body),
            'fetched_at': page.response.observation.fetched_at.isoformat(),
        } for page in result.snapshots],
    }
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 65536:
        raise ValueError('Preview report too large')
    return value
