"""Immutable crawl data contracts, independent of Flask/DB and execution policy.

These records check internal consistency, not factual accuracy or quality of a
page. Evidence references must still be verified by the executor/quality gate.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


class ContractError(ValueError):
    def __init__(self, path, code='invalid_value'):
        self.path, self.code = path, code
        super().__init__(f'{code} at {path}')


def _require(condition, path):
    if not condition:
        raise ContractError(path)


def _text(value, maximum, path, *, multiline=False):
    _require(type(value) is str and 0 < len(value) <= maximum and bool(value.strip()), path)
    _require(not any((ord(c) < 32 and not (multiline and c in '\n\r\t')) or ord(c) == 127
                     for c in value), path)
    try:
        return len(value.encode('utf-8'))
    except UnicodeError:
        raise ContractError(path) from None


def _integer(value, minimum, path):
    _require(type(value) is int and minimum <= value <= 2**31 - 1, path)


def _choice(value, choices, path):
    _require(type(value) is str and value in choices, path)


def _url(value, path):
    _text(value, 1000, path)
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {'http', 'https'} and parsed.hostname
                 and parsed.username is None and parsed.password is None and parsed.port != 0
                 and not any(c.isspace() or c == '\\' for c in value))
    except ValueError:
        valid = False
    _require(valid, path)  # Syntax only, NOT Safe Fetch permission.


def _utc(value, path):
    _require(isinstance(value, datetime) and value.utcoffset() is not None, path)
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ContractError(path) from None


def _sequence(value, cls, maximum, path):
    _require(type(value) in {list, tuple} and len(value) <= maximum, path)
    _require(all(isinstance(item, cls) for item in value), path)
    return tuple(value)


def _reference(value, path):
    _text(value, 128, path)
    _require(re.fullmatch(r'[A-Za-z0-9_:-]+', value), path)


@dataclass(frozen=True, kw_only=True)
class FieldProvenance:
    field: str
    method: str
    snapshot_id: str | None = None
    locator: str | None = field(default=None, repr=False)

    def __post_init__(self):
        _choice(self.field, {'title', 'url', 'external_id', 'content', 'author', 'image_url',
                             'published_at', 'source_language'}, 'provenance.field')
        _choice(self.method, {'css', 'feed', 'jsonld', 'legacy'}, 'provenance.method')
        if self.method != 'legacy' or self.snapshot_id is not None:
            _reference(self.snapshot_id, 'provenance.snapshot_id')
        if self.method != 'legacy' or self.locator is not None:
            _text(self.locator, 256, 'provenance.locator')


@dataclass(frozen=True, kw_only=True)
class NormalizedArticle:
    source_id: int
    external_id: str
    title: str = field(repr=False)
    url: str = field(repr=False)
    provenance: tuple[FieldProvenance, ...]
    source_language: str = 'unknown'
    content_level: str = 'metadata_only'
    content: str | None = field(default=None, repr=False)
    published_at: datetime | None = None
    published_at_source: str = 'unknown'
    author: str | None = field(default=None, repr=False)
    image_url: str | None = field(default=None, repr=False)

    def __post_init__(self):
        _integer(self.source_id, 1, 'source_id')
        _text(self.external_id, 500, 'external_id')
        _text(self.title, 500, 'title')
        _url(self.url, 'url')
        _text(self.source_language, 35, 'source_language')
        _require(re.fullmatch(r'unknown|[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}', self.source_language),
                 'source_language')
        _choice(self.content_level, {'full', 'excerpt', 'metadata_only'}, 'content_level')
        evidence = _sequence(self.provenance, FieldProvenance, 10, 'provenance')
        fields = [item.field for item in evidence]
        _require(len(fields) == len(set(fields)), 'provenance')
        required = {'title', 'url'}
        if self.content is not None:
            size = _text(self.content, 65535, 'content', multiline=True)
            _require(size <= 65535 and BeautifulSoup(self.content, 'html.parser').get_text(strip=True),
                     'content')
            required.add('content')
        _require((self.content is None) == (self.content_level == 'metadata_only'), 'content_level')
        _choice(self.published_at_source, {'unknown', 'feed', 'list', 'detail', 'jsonld', 'legacy'},
                'published_at_source')
        _require((self.published_at is None) == (self.published_at_source == 'unknown'),
                 'published_at_source')
        if self.published_at is not None:
            object.__setattr__(self, 'published_at', _utc(self.published_at, 'published_at'))
            required.add('published_at')
        if self.author is not None:
            _text(self.author, 200, 'author')
            required.add('author')
        if self.image_url is not None:
            _url(self.image_url, 'image_url')
            required.add('image_url')
        _require(required <= set(fields), 'provenance')
        object.__setattr__(self, 'provenance', evidence)


@dataclass(frozen=True, kw_only=True)
class CrawlError:
    stage: str
    code: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        codes = {
            'transport': {'timeout', 'network_error', 'rate_limited', 'server_error', 'http_error',
                          'forbidden', 'robots_denied', 'login_required', 'paywall', 'captcha',
                          'unsafe_url', 'too_large', 'redirect_limit', 'unsupported_content_type',
                          'render_unavailable', 'fetch_closed', 'tls_error', 'decode_error',
                          'budget_exceeded', 'robots_unavailable', 'transport_unavailable'},
            'extraction': {'invalid_schema', 'missing_fields', 'selector_mismatch', 'invalid_article', 'resource_limit', 'parser_unavailable'},
            'quality': {'low_quality', 'no_evidence'},
            'persistence': {'database_error'},
        }
        _choice(self.stage, codes, 'error.stage')
        _choice(self.code, codes[self.stage], 'error.code')
        references = _sequence(self.evidence_ids, str, 32, 'error.evidence_ids')
        for reference in references:
            _reference(reference, 'error.evidence_ids')
        object.__setattr__(self, 'evidence_ids', references)

    @property
    def retryable(self) -> bool:
        return self.code in {'timeout', 'network_error', 'rate_limited', 'server_error', 'database_error'}


@dataclass(frozen=True, kw_only=True)
class FetchObservation:
    requested_url: str = field(repr=False)
    fetched_at: datetime
    final_url: str | None = field(default=None, repr=False)
    http_status: int | None = None
    snapshot_id: str | None = None
    response_bytes: int = 0
    content_type: str | None = None
    error: CrawlError | None = None

    def __post_init__(self):
        _url(self.requested_url, 'requested_url')
        if self.final_url is not None:
            _url(self.final_url, 'final_url')
        if self.http_status is not None:
            _integer(self.http_status, 100, 'http_status')
            _require(self.http_status <= 599 and self.final_url is not None, 'http_status')
        if self.snapshot_id is not None:
            _reference(self.snapshot_id, 'snapshot_id')
        _integer(self.response_bytes, 0, 'response_bytes')
        if self.content_type is not None:
            _text(self.content_type, 100, 'content_type')
        if self.error is not None:
            _require(isinstance(self.error, CrawlError) and self.error.stage == 'transport', 'error')
            if self.http_status in {401, 403}:
                _require(self.status == 'blocked', 'error')
            if self.http_status == 429:
                _require(self.error.code == 'rate_limited', 'error')
        else:
            _require(self.http_status is not None and (200 <= self.http_status < 300 or self.http_status == 304),
                     'http_status')
            if self.http_status != 304:
                _require(self.snapshot_id is not None, 'snapshot_id')
        if self.http_status == 304:
            _require(self.response_bytes == 0, 'response_bytes')
        object.__setattr__(self, 'fetched_at', _utc(self.fetched_at, 'fetched_at'))

    @property
    def status(self) -> str:
        if self.error is not None:
            if self.error.code in {'forbidden', 'robots_denied', 'login_required', 'paywall',
                                    'captcha', 'unsafe_url'}:
                return 'blocked'
            return 'retryable_error' if self.error.retryable else 'failed'
        return 'not_modified' if self.http_status == 304 else 'ok'


@dataclass(frozen=True, kw_only=True)
class QualityReport:
    """Counters, not a model-provided quality score or ingestion permission."""

    discovered: int = 0
    extracted: int = 0
    valid: int = 0
    duplicate: int = 0
    new: int = 0
    updated: int = 0
    rejected: int = 0
    no_change_reason: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ('discovered', 'extracted', 'valid', 'duplicate', 'new', 'updated', 'rejected'):
            _integer(getattr(self, name), 0, 'quality.' + name)
        _require(self.valid + self.rejected == self.extracted <= self.discovered, 'quality.counts')
        _require(self.duplicate + self.new + self.updated <= self.valid, 'quality.counts')
        if self.no_change_reason is not None:
            _choice(self.no_change_reason, {'not_modified', 'confirmed_empty', 'all_duplicates'},
                    'quality.no_change_reason')
            _require(self.new == self.updated == self.rejected == 0, 'quality.no_change_reason')
            if self.no_change_reason == 'all_duplicates':
                _require(self.discovered == self.extracted == self.valid == self.duplicate > 0,
                         'quality.no_change_reason')
            else:
                _require(self.discovered == 0, 'quality.no_change_reason')
            _require(bool(self.evidence_ids), 'quality.evidence_ids')
        references = _sequence(self.evidence_ids, str, 32, 'quality.evidence_ids')
        for reference in references:
            _reference(reference, 'quality.evidence_ids')
        object.__setattr__(self, 'evidence_ids', references)


@dataclass(frozen=True, kw_only=True)
class CrawlOutcome:
    run_id: int
    status: str
    quality: QualityReport
    article_ids: tuple[int, ...] = ()
    schema_version_id: int | None = None
    quality_report_id: int | None = None
    errors: tuple[CrawlError, ...] = ()
    repair_dispatched: bool = False

    def __post_init__(self):
        _integer(self.run_id, 1, 'run_id')
        _choice(self.status, {'success', 'no_change', 'partial', 'degraded', 'inconclusive',
                              'blocked', 'failed'}, 'status')
        _require(isinstance(self.quality, QualityReport), 'quality')
        _require(type(self.repair_dispatched) is bool, 'repair_dispatched')
        ids = _sequence(self.article_ids, int, 10000, 'article_ids')
        for article_id in ids:
            _integer(article_id, 1, 'article_ids')
        _require(len(set(ids)) == len(ids) == self.quality.new + self.quality.updated, 'article_ids')
        errors = _sequence(self.errors, CrawlError, 100, 'errors')
        for name in ('schema_version_id', 'quality_report_id'):
            if getattr(self, name) is not None:
                _integer(getattr(self, name), 1, name)
        if self.status in {'no_change', 'inconclusive', 'blocked', 'failed'}:
            _require(not ids, 'article_ids')
        if self.status in {'success', 'partial', 'degraded'}:
            _require(self.quality.valid == self.quality.new + self.quality.updated + self.quality.duplicate,
                     'quality.counts')
        if self.status == 'success':
            _require(bool(ids) and not errors and self.quality.rejected == 0
                     and self.quality.extracted == self.quality.discovered, 'status')
        elif self.status == 'partial':
            _require(self.quality.valid > 0 and (self.quality.rejected > 0 or errors), 'status')
        elif self.status == 'degraded':
            _require(self.quality.valid > 0 and any(e.code == 'low_quality' for e in errors), 'status')
        elif self.status == 'failed':
            _require(bool(errors), 'errors')
        elif self.status == 'blocked':
            _require(any(e.code in {'forbidden', 'robots_denied', 'login_required', 'paywall',
                                    'captcha', 'unsafe_url'} for e in errors), 'errors')
        if self.status == 'no_change':
            _require(self.quality.no_change_reason is not None and not errors, 'quality')
        else:
            _require(self.quality.no_change_reason is None, 'quality')
        if self.repair_dispatched:
            _require(self.status in {'partial', 'degraded', 'failed', 'inconclusive'}
                     and any(e.code in {'missing_fields', 'selector_mismatch', 'low_quality'} for e in errors),
                     'repair_dispatched')
        object.__setattr__(self, 'article_ids', ids)
        object.__setattr__(self, 'errors', errors)

    @property
    def retryable(self) -> bool:
        return self.status in {'partial', 'failed'} and any(error.retryable for error in self.errors)
