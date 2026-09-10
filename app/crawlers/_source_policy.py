"""Decode admin-owned policy snapshots against current system limits, fail closed."""
from dataclasses import asdict
import hashlib
import json

from ._preview import preview_policy, source_fingerprint


def document(policy, quality, kind):
    return json.loads(json.dumps({'format': 'source-policy.v1', 'action': 'grant', 'quality_kind': kind,
                                  'fetch_policy': asdict(policy), 'quality_profile': asdict(quality)}))


def _encoded(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > 8192:
        raise ValueError('Policy too large')
    return data


def fingerprint(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def inputs(record):
    value = record.document
    if value == {'format': 'source-policy.v1', 'action': 'revoke'} and fingerprint(value) == record.document_hash:
        return None
    policy, quality = preview_policy('\n'.join(value['fetch_policy']['allowed_hosts']), value['quality_kind'])
    if _encoded(document(policy, quality, value['quality_kind'])) != _encoded(value) or fingerprint(value) != record.document_hash:
        raise ValueError('Incompatible source policy')
    return policy, quality


def latest(profile):
    from app.models.crawl_schema import CrawlPolicyVersion
    if profile is None:
        return None
    # state() also requires the control marker to agree: neither a missing
    # decision nor a missing/reverted marker may restore an older grant.
    return (CrawlPolicyVersion.query.filter_by(profile_id=profile.id)
            .order_by(CrawlPolicyVersion.generation.desc()).first())


def state(record, source, profile):
    if record is None:
        return 'unavailable' if profile and profile.policy_generation is not None else 'unconfigured'
    if record.generation != profile.policy_generation:
        return 'unavailable'
    try:
        if inputs(record) is None:
            return 'revoked'
    except (ValueError, KeyError, TypeError, RecursionError):
        return 'unavailable'
    if (not source.is_active or record.source_generation != profile.source_generation
            or record.source_fingerprint != source_fingerprint(source)):
        return 'stale'
    return 'effective'


def reference_id(value):
    if (type(value) is dict and set(value) == {'id', 'hash'}
            and type(value['id']) is int and 0 < value['id'] < 2 ** 31
            and isinstance(value['hash'], str) and len(value['hash']) == 64
            and all(char in '0123456789abcdef' for char in value['hash'])):
        return value['id']
    return None


def matches_report(record, source, profile, data):
    status = state(record, source, profile)
    reference = data.get('source_policy')
    if status == 'unconfigured':
        return reference is None
    if status != 'effective' or reference_id(reference) is None:
        return False
    try:
        return (reference == {'id': record.id, 'hash': record.document_hash}
                and _encoded(data['fetch_policy']) == _encoded(record.document['fetch_policy'])
                and _encoded(data['quality_profile']) == _encoded(record.document['quality_profile']))
    except (ValueError, KeyError, TypeError, RecursionError):
        return False
