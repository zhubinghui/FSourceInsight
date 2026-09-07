"""Declarative recipe import. Validation is NOT permission to fetch or publish."""
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bs4 import BeautifulSoup


class InvalidRecipe(ValueError):
    """Stable code/path without echoing untrusted field names or values."""

    def __init__(self, code: str, path: str = '$'):
        self.code, self.path = code, path
        super().__init__(f'{code} at {path}')


@dataclass(frozen=True)
class ValidatedRecipe:
    """Import via validate_recipe; exported dictionaries are independent copies."""

    _canonical: str = field(repr=False)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self._canonical.encode('utf-8')).hexdigest()

    def to_dict(self) -> dict:
        return json.loads(self._canonical)


def validate_recipe(document: str | dict) -> ValidatedRecipe:
    """Validate v1 structure only; no fetching, extraction, policy changes or approval."""
    if type(document) is str:
        _json_size(document)
        try:
            document = json.loads(document, object_pairs_hook=_unique_keys,
                                  parse_constant=_bad_constant)
        except InvalidRecipe:
            raise
        except (ValueError, RecursionError):
            raise InvalidRecipe('invalid_json') from None
    _bounded_json(document)
    try:
        canonical = json.dumps(document, sort_keys=True, ensure_ascii=False,
                               allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError):
        raise InvalidRecipe('invalid_json') from None
    _json_size(canonical)
    _structure(document)
    pages = document.get('list_pages', []) + document.get('detail_templates', [])
    field_count = sum(len(page['fields']) for page in pages) + len(document.get('feed', {}).get('fields', {}))
    selector_count = sum(
        len(page['fields']) + len(page.get('remove_selectors', []))
        + ('item_selector' in page) + ('pagination' in page) for page in pages
    )
    if field_count > 64 or selector_count > 128:
        raise InvalidRecipe('limit_exceeded')
    return ValidatedRecipe(canonical)


def _json_size(value):
    if len(value) > 65536:
        raise InvalidRecipe('limit_exceeded')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise InvalidRecipe('invalid_json') from None
    if size > 65536:
        raise InvalidRecipe('limit_exceeded')
    return size


def _bad_constant(value):
    raise InvalidRecipe('invalid_json')


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidRecipe('duplicate_key')
        result[key] = value
    return result


def _bounded_json(value):
    # Bounds precede serialization/structural walking; also rejects cycles and
    # Python-only objects without calling their conversion hooks.
    remaining = 2048
    remaining_bytes = 65536

    def visit(item, depth):
        nonlocal remaining, remaining_bytes
        remaining -= 1
        remaining_bytes -= 1
        if depth > 12 or remaining < 0:
            raise InvalidRecipe('limit_exceeded')
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise InvalidRecipe('invalid_json')
                remaining_bytes -= _json_size(key) + 3
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            remaining_bytes -= _json_size(item) + 2
        elif type(item) is float:
            if not math.isfinite(item):
                raise InvalidRecipe('invalid_json')
        elif item is not None and type(item) not in {int, bool}:
            raise InvalidRecipe('invalid_json')
        if remaining_bytes < 0:
            raise InvalidRecipe('limit_exceeded')

    visit(value, 0)


def _object(value, required, optional, path):
    if type(value) is not dict:
        raise InvalidRecipe('invalid_type', path)
    if not required <= value.keys() or value.keys() - required - optional:
        raise InvalidRecipe('invalid_fields', path)


def _fields(value, required, path, *, jsonld=False):
    _object(value, required, {'title', 'url', 'content', 'external_id', 'published_at',
                              'author', 'image_url'}, path)
    if not value:
        raise InvalidRecipe('invalid_fields', path)
    for name, rule in value.items():
        rule_path = f'{path}.{name}'
        if jsonld and type(rule) is dict and rule.get('read') == 'jsonld':
            _object(rule, {'read', 'path'}, set(), rule_path)
            allowed_paths = {
                'title': [['headline'], ['name']], 'url': [['url'], ['@id']],
                'content': [['articleBody'], ['description']], 'external_id': [['@id'], ['url']],
                'published_at': [['datePublished']], 'author': [['author', 'name']],
                'image_url': [['image'], ['image', 'url']],
            }
            if rule['path'] not in allowed_paths[name]:
                raise InvalidRecipe('invalid_jsonld_path', rule_path + '.path')
            continue
        _object(rule, {'selector', 'read'}, {'attr'}, rule_path)
        _selector(rule['selector'], rule_path + '.selector')
        _choice(rule['read'], {'text', 'paragraphs', 'attr'}, rule_path + '.read')
        if rule['read'] == 'attr':
            _choice(rule.get('attr'), {'href', 'src', 'datetime', 'content', 'title', 'id'},
                    rule_path + '.attr')
        elif 'attr' in rule:
            raise InvalidRecipe('invalid_fields', rule_path)


def _structure(doc):
    if type(doc) is not dict:
        raise InvalidRecipe('invalid_type')
    extractor = doc.get('extractor', 'html')
    _choice(extractor, {'html', 'rss'}, '$.extractor')
    _object(doc, {'format_version', 'output_contract', 'target_kind', 'source_id',
                  'locale', 'transport', 'identity_policy',
                  'feed' if extractor == 'rss' else 'list_pages'},
            {'detail_templates', 'date_policy', 'extractor'}, '$')
    _integer(doc['format_version'], 1, 1, '$.format_version')
    _integer(doc['source_id'], 1, 2**31 - 1, '$.source_id')
    for name, choices in {
        'output_contract': {'article.v1'}, 'target_kind': {'news'}, 'transport': {'http'},
        'identity_policy': {'legacy-compatible-url-v1'},
    }.items():
        _choice(doc[name], choices, '$.' + name)
    _text(doc['locale'], 35, '$.locale')
    if not re.fullmatch(r'unknown|[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}', doc['locale']):
        raise InvalidRecipe('invalid_language', '$.locale')
    if extractor == 'rss':
        _object(doc['feed'], {'url', 'fields'}, set(), '$.feed')
        _url(doc['feed']['url'], '$.feed.url')
        mapping = {
            'title': {'title'}, 'url': {'link'}, 'external_id': {'id', 'link'},
            'content': {'content', 'summary'}, 'published_at': {'published', 'updated'},
            'author': {'author'},
        }
        _object(doc['feed']['fields'], {'title', 'url'}, set(mapping), '$.feed.fields')
        for name, value in doc['feed']['fields'].items():
            _choice(value, mapping[name], '$.feed.fields.' + name)
    else:
        _array(doc['list_pages'], 1, 4, '$.list_pages')
    for i, page in enumerate(doc.get('list_pages', [])):
        path = f'$.list_pages[{i}]'
        _object(page, {'url', 'item_selector', 'fields'}, {'pagination'}, path)
        _url(page['url'], path + '.url')
        _selector(page['item_selector'], path + '.item_selector')
        _fields(page['fields'], {'title', 'url'}, path + '.fields')
        if 'pagination' in page:
            _object(page['pagination'], {'kind', 'selector', 'max_pages'}, set(), path + '.pagination')
            _choice(page['pagination']['kind'], {'next_link'}, path + '.pagination.kind')
            _integer(page['pagination']['max_pages'], 1, 10, path + '.pagination.max_pages')
            _selector(page['pagination']['selector'], path + '.pagination.selector')
    _array(doc.get('detail_templates', []), 0, 8, '$.detail_templates')
    for i, template in enumerate(doc.get('detail_templates', [])):
        path = f'$.detail_templates[{i}]'
        _object(template, {'match', 'fields'}, {'remove_selectors', 'jsonld_types'}, path)
        if 'jsonld_types' in template:
            _array(template['jsonld_types'], 1, 3, path + '.jsonld_types')
            for kind in template['jsonld_types']:
                _choice(kind, {'Article', 'NewsArticle', 'Event'}, path + '.jsonld_types')
        _object(template['match'], {'host', 'path_prefix'}, set(), path + '.match')
        host, prefix = template['match']['host'], template['match']['path_prefix']
        _text(host, 253, path + '.match.host')
        if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', host):
            raise InvalidRecipe('invalid_host', path + '.match.host')
        _text(prefix, 1000, path + '.match.path_prefix')
        if not prefix.startswith('/') or prefix.startswith('//') or any(c in prefix for c in '?#\\'):
            raise InvalidRecipe('invalid_path', path + '.match.path_prefix')
        _fields(template['fields'], set(), path + '.fields', jsonld='jsonld_types' in template)
        _array(template.get('remove_selectors', []), 0, 16, path + '.remove_selectors')
        for selector in template.get('remove_selectors', []):
            _selector(selector, path + '.remove_selectors')
    if 'date_policy' in doc:
        _object(doc['date_policy'], {'source_timezone'}, set(), '$.date_policy')
        zone = doc['date_policy']['source_timezone']
        _text(zone, 100, '$.date_policy.source_timezone')
        try:
            ZoneInfo(zone)
        except (ValueError, ZoneInfoNotFoundError):
            raise InvalidRecipe('invalid_timezone', '$.date_policy.source_timezone') from None


def _selector(value, path):
    _text(value, 256, path)
    # Deliberately small CSS subset: descendants/children, tags, classes, IDs,
    # attributes. No lists, escapes, pseudo-classes, regex or sibling traversal.
    outside, quoted, bracket = [], None, False
    for char in value:
        if char == '\\':
            raise InvalidRecipe('invalid_selector', path)
        if quoted:
            if char == quoted:
                quoted = None
        elif bracket:
            if char in '\"\'':
                quoted = char
            elif char == ']':
                bracket = False
            elif char == '[':
                raise InvalidRecipe('invalid_selector', path)
        elif char == '[':
            bracket = True
        elif char.isascii() and (char.isalnum() or char in ' .#_*>-'):
            outside.append(char)
        else:
            raise InvalidRecipe('invalid_selector', path)
    if quoted or bracket or len(re.findall(r'[ >]+', ''.join(outside).strip())) > 7:
        raise InvalidRecipe('invalid_selector', path)
    try:
        # Public BS4 selector parser against an empty document, not fetched DOM.
        BeautifulSoup('', 'html.parser').select(value)
    except (ValueError, SyntaxError, NotImplementedError):
        raise InvalidRecipe('invalid_selector', path) from None


def _choice(value, choices, path):
    if type(value) is not str or value not in choices:
        raise InvalidRecipe('unsupported_value', path)


def _integer(value, low, high, path):
    if type(value) is not int or not low <= value <= high:
        raise InvalidRecipe('invalid_integer', path)


def _text(value, maximum, path):
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise InvalidRecipe('invalid_text', path)


def _array(value, minimum, maximum, path):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise InvalidRecipe('invalid_array', path)


def _url(value, path):
    # Syntax only. Safe Fetch must separately check source permission, DNS and redirects.
    _text(value, 1000, path)
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {'https', 'http'} and parsed.hostname
                 and parsed.username is None and parsed.password is None
                 and parsed.port != 0 and not any(c.isspace() or c == '\\' for c in value))
    except ValueError:
        valid = False
    if not valid:
        raise InvalidRecipe('invalid_url', path)
