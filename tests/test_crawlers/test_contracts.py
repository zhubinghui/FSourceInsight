"""Standard crawl result interface; no database or collaborator mocks."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest


def test_metadata_article_keeps_identity_unknowns_and_immutable_evidence():
    from app.crawlers.contracts import FieldProvenance, NormalizedArticle

    evidence = [FieldProvenance(field='title', method='css', snapshot_id='page-1', locator='h1'),
                FieldProvenance(field='url', method='css', snapshot_id='page-1', locator='a[href]')]
    article = NormalizedArticle(source_id=42, external_id='old-guid-001', title='Actualité',
                                url='https://news.example.invalid/1', provenance=evidence)
    evidence.clear()
    assert article.external_id == 'old-guid-001'
    assert article.source_language == 'unknown'
    assert article.content_level == 'metadata_only' and article.content is None
    assert article.published_at is None and article.published_at_source == 'unknown'
    assert len(article.provenance) == 2
    with pytest.raises(FrozenInstanceError):
        article.content_level = 'full'


@pytest.fixture
def article_values():
    from app.crawlers.contracts import FieldProvenance

    return dict(source_id=42, external_id='old-guid-001', title='Actualité',
                url='https://news.example.invalid/1', provenance=(
                    FieldProvenance(field='title', method='css', snapshot_id='page-1', locator='h1'),
                    FieldProvenance(field='url', method='css', snapshot_id='page-1', locator='a'),
                ))


@pytest.mark.parametrize('changes', [
    {'source_id': True}, {'source_id': 0}, {'external_id': ''},
    {'external_id': 'x' * 501}, {'title': ' '}, {'title': 'é' * 501},
    {'url': 'file:///etc/passwd'}, {'url': 'https://u:p@news.example.invalid/'},
    {'source_language': 'French'}, {'content_level': 'complete'},
    {'content_level': 'full'}, {'content_level': 'excerpt', 'content': '   '},
    {'content_level': 'full', 'content': '<p> </p>'},
    {'content_level': 'metadata_only', 'content': 'unlabelled excerpt'},
    {'content_level': 'full', 'content': 'é' * 32768},
    {'content_level': 'full', 'content': 'No provenance for this content'},
    {'provenance': ()}, {'provenance': ['not evidence']},
    {'published_at': datetime(2026, 9, 6)},
    {'published_at_source': 'detail'},
    {'published_at': datetime(2026, 9, 6, tzinfo=timezone.utc)},
])
def test_invalid_or_mislabelled_article_is_rejected(article_values, changes):
    from app.crawlers.contracts import NormalizedArticle

    with pytest.raises(ValueError):
        NormalizedArticle(**(article_values | changes))


def test_known_publication_time_is_utc_and_not_replaced_with_fetch_time(article_values):
    from app.crawlers.contracts import FieldProvenance, NormalizedArticle

    article_values['provenance'] += (
        FieldProvenance(field='published_at', method='feed', snapshot_id='feed-1', locator='published'),
        FieldProvenance(field='content', method='feed', snapshot_id='feed-1', locator='summary'),
    )
    article = NormalizedArticle(**article_values, source_language='fr',
                                content_level='excerpt', content='Une courte actualité.',
                                published_at=datetime(2026, 9, 6, 9, 15, tzinfo=timezone(timedelta(hours=2))),
                                published_at_source='feed')
    assert article.published_at == datetime(2026, 9, 6, 7, 15, tzinfo=timezone.utc)
    assert article.published_at.tzinfo is timezone.utc
    assert article.content_level == 'excerpt'
    with pytest.raises(ValueError):
        replace(article, provenance=article.provenance + (article.provenance[0],))


def test_text_limit_counts_utf8_bytes_without_truncation(article_values):
    from app.crawlers.contracts import FieldProvenance, NormalizedArticle

    article_values['provenance'] += (
        FieldProvenance(field='content', method='css', snapshot_id='page-1', locator='article'),
    )
    article = NormalizedArticle(**article_values, content_level='full', content='é' * 32767 + 'a')
    assert article.content.endswith('éa')
    with pytest.raises(ValueError):
        replace(article, content='é' * 32768)


@pytest.mark.parametrize('changes', [
    {'field': 'password'}, {'method': 'eval'}, {'snapshot_id': None},
    {'snapshot_id': '../../etc/passwd'}, {'locator': None}, {'locator': 'x' * 257},
])
def test_field_evidence_has_a_known_method_and_bounded_locator(changes):
    from app.crawlers.contracts import FieldProvenance

    values = dict(field='title', method='css', snapshot_id='page-1', locator='h1')
    with pytest.raises(ValueError):
        FieldProvenance(**(values | changes))


def test_fetch_observation_keeps_final_url_and_classifies_transport_failure():
    from app.crawlers.contracts import CrawlError, FetchObservation

    observation = FetchObservation(
        requested_url='https://news.example.invalid/old', final_url='https://news.example.invalid/new',
        fetched_at=datetime(2026, 9, 6, 9, tzinfo=timezone(timedelta(hours=2))),
        http_status=200, snapshot_id='page-1', response_bytes=1200, content_type='text/html',
    )
    assert observation.final_url.endswith('/new') and observation.status == 'ok'
    assert observation.fetched_at.hour == 7 and observation.fetched_at.tzinfo is timezone.utc
    failed = replace(observation, http_status=429, error=CrawlError(stage='transport', code='rate_limited'))
    assert failed.status == 'retryable_error' and failed.error.retryable
    blocked = replace(observation, http_status=403, error=CrawlError(stage='transport', code='forbidden'))
    assert blocked.status == 'blocked' and not blocked.error.retryable
    not_modified = replace(observation, http_status=304, snapshot_id=None, response_bytes=0)
    assert not_modified.status == 'not_modified'


@pytest.mark.parametrize('changes', [
    {'http_status': 403}, {'http_status': None}, {'http_status': True},
    {'snapshot_id': None}, {'final_url': None}, {'response_bytes': -1},
    {'requested_url': 'file:///etc/passwd'}, {'final_url': 'https://user:pass@host.invalid/'},
    {'snapshot_id': '../outside'}, {'content_type': 'text/html\nsecret'},
    {'error': 'timeout'}, {'http_status': 304, 'response_bytes': 10},
])
def test_fetch_without_consistent_transport_evidence_is_not_success(changes):
    from app.crawlers.contracts import FetchObservation

    values = dict(requested_url='https://news.example.invalid/', final_url='https://news.example.invalid/',
                  fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc), http_status=200,
                  snapshot_id='page-1', response_bytes=0, content_type='text/html')
    with pytest.raises(ValueError):
        FetchObservation(**(values | changes))


@pytest.mark.parametrize('values', [
    {'stage': 'execute', 'code': 'timeout'}, {'stage': 'quality', 'code': 'timeout'},
    {'stage': 'transport', 'code': 'run_script'},
    {'stage': 'transport', 'code': 'timeout', 'evidence_ids': ['../../private']},
])
def test_structured_errors_cannot_invent_stages_or_retry_semantics(values):
    from app.crawlers.contracts import CrawlError

    with pytest.raises(ValueError):
        CrawlError(**values)


def test_all_duplicates_is_evidenced_no_change_not_a_repair_request():
    from app.crawlers.contracts import CrawlOutcome, QualityReport

    report = QualityReport(discovered=2, extracted=2, valid=2, duplicate=2,
                           no_change_reason='all_duplicates', evidence_ids=['list-1'])
    result = CrawlOutcome(run_id=7, status='no_change', quality=report)
    assert result.article_ids == () and not result.repair_dispatched and not result.retryable
    assert result.quality.evidence_ids == ('list-1',)
    with pytest.raises(ValueError):
        replace(result, repair_dispatched=True)
    with pytest.raises(ValueError):
        CrawlOutcome(run_id=8, status='no_change', quality=QualityReport())
    inconclusive = CrawlOutcome(run_id=8, status='inconclusive', quality=QualityReport())
    assert inconclusive.status == 'inconclusive'


@pytest.mark.parametrize('values', [
    {'discovered': -1}, {'valid': True}, {'extracted': 1},
    {'discovered': 1, 'extracted': 1},
    {'discovered': 1, 'extracted': 1, 'valid': 1, 'duplicate': 1, 'new': 1},
    {'no_change_reason': 'because-agent-says-so', 'evidence_ids': ['page-1']},
    {'no_change_reason': 'all_duplicates', 'evidence_ids': ['page-1']},
    {'no_change_reason': 'confirmed_empty'},
])
def test_quality_counters_and_no_change_reasons_must_be_consistent(values):
    from app.crawlers.contracts import QualityReport

    with pytest.raises(ValueError):
        QualityReport(**values)


def test_partial_run_keeps_valid_ids_but_transport_alone_cannot_trigger_learning():
    from app.crawlers.contracts import CrawlError, CrawlOutcome, QualityReport

    report = QualityReport(discovered=3, extracted=2, valid=1, new=1, rejected=1)
    ids = [101]
    partial = CrawlOutcome(run_id=7, status='partial', quality=report, article_ids=ids,
                           errors=[CrawlError(stage='extraction', code='missing_fields')],
                           repair_dispatched=True)
    ids.clear()
    assert partial.article_ids == (101,) and partial.repair_dispatched
    network = CrawlOutcome(run_id=8, status='failed', quality=QualityReport(),
                           errors=[CrawlError(stage='transport', code='timeout')])
    assert network.retryable and not network.repair_dispatched
    with pytest.raises(ValueError):
        replace(network, repair_dispatched=True)


@pytest.mark.parametrize('changes', [
    {'status': 'made_up'}, {'status': 'failed'}, {'status': 'blocked'},
    {'status': 'no_change'}, {'run_id': True}, {'article_ids': [True]},
    {'article_ids': []}, {'article_ids': [101, 101]}, {'quality': {}},
    {'errors': ['error']}, {'repair_dispatched': 'yes'}, {'schema_version_id': 0},
])
def test_outcome_rejects_conflicting_status_or_uncommitted_ids(changes):
    from app.crawlers.contracts import CrawlOutcome, QualityReport

    values = dict(run_id=7, status='success', article_ids=[101],
                  quality=QualityReport(discovered=1, extracted=1, valid=1, new=1))
    assert CrawlOutcome(**values).article_ids == (101,)
    with pytest.raises(ValueError):
        CrawlOutcome(**(values | changes))


def test_forbidden_http_status_cannot_be_labelled_as_retryable_timeout():
    from app.crawlers.contracts import CrawlError, FetchObservation

    with pytest.raises(ValueError):
        FetchObservation(requested_url='https://news.example.invalid/',
                         final_url='https://news.example.invalid/', http_status=403,
                         fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
                         error=CrawlError(stage='transport', code='timeout'))


def test_success_cannot_silently_drop_a_valid_article_from_accounting():
    from app.crawlers.contracts import CrawlOutcome, QualityReport

    with pytest.raises(ValueError):
        CrawlOutcome(run_id=7, status='success', article_ids=[101],
                     quality=QualityReport(discovered=2, extracted=2, valid=2, new=1))
