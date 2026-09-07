"""Deterministic news execution; preview never accesses the business database."""
from dataclasses import dataclass, field
import hashlib
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from .contracts import ContractError, CrawlError, CrawlOutcome, FetchObservation, FieldProvenance, NormalizedArticle, QualityReport
from .fetcher import FetchError, FetchPolicy, FetchResponse, SafeFetcher
from ._fetch_policy import Rejected, canonical_url
from .schema import ValidatedRecipe, validate_recipe
from .quality import QualityProfile, below_baseline, body_matches, content_level, parse_date, titles_match

__all__ = ['CrawlEngine', 'CrawlPreview', 'PageSnapshot', 'QualityProfile']
from ._parser import parse


@dataclass(frozen=True)
class PageSnapshot:
    url: str = field(repr=False)
    response: FetchResponse = field(repr=False)


@dataclass(frozen=True)
class CrawlPreview:
    articles: tuple = field(repr=False)
    quality: QualityReport
    observations: tuple
    errors: tuple = ()
    status: str = 'ready'
    snapshots: tuple = field(default=(), repr=False)


_ACCESS = {'forbidden', 'robots_denied', 'unsafe_url', 'login_required', 'paywall', 'captcha'}


def _parser_error(exc):
    code = str(exc) if str(exc) in _ACCESS | {'resource_limit', 'parser_unavailable', 'low_quality', 'missing_fields'} else 'invalid_article'
    return CrawlError(stage='transport' if code in _ACCESS else 'quality' if code == 'low_quality' else 'extraction', code=code)


def _redacted(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


class _PageFailure(Exception):
    def __init__(self, error):
        self.error = error


class CrawlEngine:
    VERSION = 'news-engine.v1'

    def __init__(self, source_id, *, recipe=None, fetch_policy, snapshots=None, profile=None, legacy=None):
        if legacy is not None:
            if recipe is not None:
                raise ValueError('Choose recipe or legacy adapter')
            from ._legacy import recipe_for
            recipe = recipe_for(legacy)
        self.source_id = source_id
        self.recipe = validate_recipe(recipe.to_dict() if isinstance(recipe, ValidatedRecipe) else recipe)
        if type(source_id) is not int or source_id != self.recipe.to_dict()['source_id']:
            raise ValueError('Recipe source mismatch')
        if type(fetch_policy) is not FetchPolicy or profile is not None and type(profile) is not QualityProfile:
            raise ValueError('Invalid system policy/profile')
        self.fetch_policy = fetch_policy
        self.profile = profile or QualityProfile()
        if snapshots is not None:
            if (type(snapshots) not in {list, tuple} or len(snapshots) > 16
                    or any(type(p) is not PageSnapshot or type(p.url) is not str
                           or type(p.response) is not FetchResponse or type(p.response.body) is not bytes
                           or type(p.response.document_url) is not str
                           or type(p.response.observation) is not FetchObservation for p in snapshots)):
                raise ValueError('Invalid snapshots')
            if len({p.url for p in snapshots}) != len(snapshots) or sum(len(p.response.body) for p in snapshots) > 8 * 1024 * 1024:
                raise ValueError('Invalid snapshots')
            try:
                if any(canonical_url(p.url, fetch_policy.allowed_hosts) != p.url or
                       canonical_url(p.response.document_url, fetch_policy.allowed_hosts) != p.response.document_url for p in snapshots):
                    raise ValueError('Invalid snapshots')
            except Rejected:
                raise ValueError('Invalid snapshots') from None
        self.snapshots = None if snapshots is None else tuple(snapshots)

    def run(self) -> CrawlOutcome:
        if self.snapshots is not None:
            raise ValueError('Replay is preview-only')
        from ._ingestion import run
        return run(self)

    def preview(self) -> CrawlPreview:
        doc = self.recipe.to_dict()
        deadline = time.monotonic() + self.fetch_policy.max_seconds
        articles, observations, errors, captured = [], [], [], []
        discovered = extracted = rejected = duplicates = 0
        confirmed_empty = exhausted = False
        rss = doc.get('extractor') == 'rss'
        seen_articles, loaded = set(), {}
        replay = None if self.snapshots is None else {p.url: p.response for p in self.snapshots}
        with SafeFetcher(self.fetch_policy) as fetcher:
            def load(url):
                url = canonical_url(url, self.fetch_policy.allowed_hosts)
                if url in loaded:
                    return loaded[url]
                if replay is not None:
                    if url not in replay:
                        raise _PageFailure(CrawlError(stage='quality', code='no_evidence'))
                    response = replay[url]
                    obs = response.observation
                    if (obs.status != 'ok' or obs.requested_url != _redacted(url)
                            or obs.final_url != _redacted(response.document_url)
                            or not obs.snapshot_id or obs.snapshot_id != 'sha256:' + hashlib.sha256(response.body).hexdigest()
                            or obs.response_bytes != len(response.body)
                            or canonical_url(response.document_url, self.fetch_policy.allowed_hosts) != response.document_url):
                        raise _PageFailure(CrawlError(stage='quality', code='no_evidence'))
                else:
                    response = fetcher.fetch(url)
                if response.observation.status != 'ok':
                    observations.append(response.observation)
                    raise _PageFailure(CrawlError(stage='quality', code='no_evidence'))
                loaded[url] = response
                observations.append(response.observation)
                captured.append(PageSnapshot(url, response))
                return response

            for list_index, page in enumerate([doc['feed']] if rss else doc['list_pages']):
                if exhausted:
                    break
                url, visited = page['url'], set()
                pagination = page.get('pagination')
                for page_index in range(pagination['max_pages'] if pagination else 1):
                    if extracted >= 200 or time.monotonic() >= deadline:
                        errors.append(CrawlError(stage='extraction', code='resource_limit'))
                        exhausted = True
                        break
                    try:
                        url = canonical_url(url, self.fetch_policy.allowed_hosts)
                        if url in visited:
                            raise Rejected('redirect_limit')
                        visited.add(url)
                        response = load(url)
                    except (FetchError, Rejected, _PageFailure) as exc:
                        errors.append(exc.error if hasattr(exc, 'error') else CrawlError(stage='transport', code=exc.code))
                        break
                    try:
                        records, next_link, empty = parse(response.body, page, kind='list', rss=rss,
                            deadline=min(deadline, time.monotonic() + self.profile.max_parse_seconds))
                        confirmed_empty = confirmed_empty or empty
                        if not rss and not records:
                            errors.append(CrawlError(stage='quality', code='no_evidence'))
                    except ValueError as exc:
                        errors.append(_parser_error(exc))
                        break
                    discovered += len(records)
                    for item_index, values in enumerate(records):
                        if extracted >= 200 or time.monotonic() >= deadline:
                            errors.append(CrawlError(stage='extraction', code='resource_limit'))
                            exhausted = True
                            break
                        extracted += 1
                        try:
                            if not values.get('title') or not values.get('url'):
                                raise ValueError('missing_fields')
                            legacy_url = urljoin(response.document_url, values['url'])
                            link = canonical_url(legacy_url, self.fetch_policy.allowed_hosts)
                            if link in seen_articles:
                                duplicates += 1
                                continue
                            values['url'] = link
                            if '_content_error' in values:
                                errors.append(_parser_error(ValueError(values.pop('_content_error'))))
                            full_candidate = rss and doc['feed']['fields'].get('content') == 'content' and bool(values.get('content'))
                            if full_candidate and not body_matches(values['title'], values['content']):
                                values.pop('content')
                                full_candidate = False
                                errors.append(CrawlError(stage='quality', code='low_quality'))
                            evidence = {name: FieldProvenance(field=name, method='feed' if rss else 'css',
                                        snapshot_id=response.observation.snapshot_id,
                                        locator=f'doc:{hashlib.sha256(response.document_url.encode()).hexdigest()}:list:{list_index}:page:{page_index}:item:{item_index}:{name}') for name in values}
                            date_source = 'feed' if rss else 'list'
                            templates = sorted((t for t in doc.get('detail_templates', [])
                                if urlsplit(link).hostname == t['match']['host'] and urlsplit(link).path.startswith(t['match']['path_prefix'])),
                                key=lambda t: len(t['match']['path_prefix']), reverse=True)
                            if full_candidate and content_level(values.get('content'), self.profile) == 'full':
                                templates = []
                            if len(templates) > 1 and templates[0]['match'] == templates[1]['match']:
                                errors.append(CrawlError(stage='extraction', code='invalid_schema'))
                                templates = []
                            for template in templates[:1]:
                                match = template['match']
                                if urlsplit(link).hostname != match['host'] or not urlsplit(link).path.startswith(match['path_prefix']):
                                    continue
                                try:
                                    detail = load(link)
                                    if (urlsplit(detail.document_url).hostname != match['host']
                                            or not urlsplit(detail.document_url).path.startswith(match['path_prefix'])):
                                        raise ValueError('missing_fields')
                                    fields = parse(detail.body, template, kind='detail', url=detail.document_url,
                                        deadline=min(deadline, time.monotonic() + self.profile.max_parse_seconds))
                                    if any(name in template['fields'] and name not in fields for name in ('title', 'content')):
                                        raise ValueError('missing_fields')
                                    if fields.get('title') and not titles_match(values['title'], fields['title']):
                                        errors.append(CrawlError(stage='quality', code='low_quality'))
                                        break
                                    if fields.get('content') and not body_matches(values['title'], fields['content']):
                                        raise ValueError('low_quality')
                                    full_candidate = bool(fields.get('content')) and template['fields'].get('content', {}).get('path') != ['description']
                                    for name, value in fields.items():
                                        if name in {'url', 'external_id'}:
                                            continue  # Detail canonical metadata never rewrites list identity.
                                        values[name] = urljoin(detail.document_url, value) if name == 'image_url' else value
                                        evidence[name] = FieldProvenance(field=name,
                                            method='jsonld' if template['fields'][name]['read'] == 'jsonld' else 'css',
                                            snapshot_id=detail.observation.snapshot_id,
                                            locator=f'doc:{hashlib.sha256(detail.document_url.encode()).hexdigest()}:detail:{doc["detail_templates"].index(template)}:{name}')
                                        if name == 'published_at':
                                            date_source = 'detail'
                                except (FetchError, Rejected, _PageFailure) as exc:
                                    errors.append(exc.error if hasattr(exc, 'error') else CrawlError(stage='transport', code=exc.code))
                                except ValueError as exc:
                                    errors.append(_parser_error(exc))
                                break
                            published_at = parse_date(values.get('published_at'), doc.get('date_policy', {}).get('source_timezone'))
                            if values.get('image_url'):
                                values['image_url'] = canonical_url(urljoin(response.document_url, values['image_url']), self.fetch_policy.allowed_hosts)
                            content = values.get('content')
                            article = NormalizedArticle(source_id=self.source_id, title=values['title'], url=link,
                                external_id=values.get('external_id') or hashlib.sha256(legacy_url.encode()).hexdigest()[:32],
                                source_language=doc['locale'], content=content,
                                content_level=content_level(content, self.profile) if full_candidate else ('excerpt' if content else 'metadata_only'),
                                published_at=published_at, published_at_source=date_source if published_at else 'unknown',
                                author=values.get('author'), image_url=values.get('image_url'), provenance=tuple(evidence.values()))
                            seen_articles.add(link)
                            articles.append(article)
                        except (ValueError, Rejected) as exc:
                            rejected += 1
                            code = 'unsafe_url' if isinstance(exc, Rejected) else (
                                'invalid_article' if isinstance(exc, ContractError) else 'missing_fields')
                            errors.append(CrawlError(stage='transport' if code == 'unsafe_url' else 'extraction',
                                                     code=code))
                    if exhausted or not next_link:
                        break
                    url = urljoin(response.document_url, next_link)
        if time.monotonic() >= deadline:
            errors.append(CrawlError(stage='extraction', code='resource_limit'))
        if below_baseline(len(articles) + duplicates, extracted, self.profile):
            errors.append(CrawlError(stage='quality', code='low_quality'))
        errors = list(dict.fromkeys(errors))  # Counts retain every rejected card; error categories are bounded.
        status = ('degraded' if errors and all(e.code == 'low_quality' for e in errors) else
                  'partial' if errors else 'ready') if articles else (
            'blocked' if any(e.code in _ACCESS for e in errors)
            else 'failed' if any(e.code != 'no_evidence' for e in errors) else 'inconclusive')
        no_change = confirmed_empty and not discovered and not errors
        if no_change:
            status = 'no_change'
        return CrawlPreview(tuple(articles), QualityReport(discovered=discovered, extracted=extracted,
                            valid=len(articles) + duplicates, rejected=rejected, duplicate=duplicates,
                            no_change_reason='confirmed_empty' if no_change else None,
                            evidence_ids=tuple(o.snapshot_id for o in observations if o.snapshot_id)[:32]),
                            tuple(observations), tuple(errors), status, tuple(captured))
