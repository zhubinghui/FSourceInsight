"""Deterministic document readers. No database or network access."""
import json
from urllib.parse import urljoin, urldefrag

import feedparser

if __package__:
    from .quality import bounded_document, clean_content, clean_document, link_noise, read_fields
else:
    from quality import bounded_document, clean_content, clean_document, link_noise, read_fields


def _invalid(value):
    raise ValueError('invalid_article')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('invalid_article')
        result[key] = value
    return result


def list_records(body, page, *, rss=False):
    if rss:
        feed = feedparser.parse(body)
        if not feed.version or feed.bozo:
            raise ValueError('invalid_article')
        records = []
        if len(feed.entries) > 200:
            raise ValueError('resource_limit')
        for entry in feed.entries:
            values = {}
            identity = entry.get('id') or entry.get('guid')
            if 'external_id' not in page['fields'] and isinstance(identity, str) and identity:
                values['external_id'] = identity
            for name, key in page['fields'].items():
                value = entry.get(key)
                if key == 'content':
                    value = value[0].get('value') if isinstance(value, list) and value else None
                if isinstance(value, str) and value.strip():
                    if name == 'content':
                        try:
                            value = clean_content(value)
                        except ValueError as exc:
                            values['_content_error'] = str(exc)
                            continue
                    values[name] = value
            records.append(values)
        return records, None, not records
    soup = clean_document(body)
    nodes = soup.select(page['item_selector'], limit=201)
    if len(nodes) > 200:
        raise ValueError('resource_limit')
    records = []
    size = 0
    for node in nodes:
        values = read_fields(node, page['fields'])
        size += sum(len(value.encode()) for value in values.values())
        if size > 1024 * 1024:
            raise ValueError('resource_limit')
        records.append(values)
    pagination = page.get('pagination')
    next_node = soup.select_one(pagination['selector']) if pagination else None
    return records, next_node.get('href') if next_node else None, False


def detail_fields(body, template, url):
    cleaned = clean_document(body, template.get('remove_selectors', []))
    values = read_fields(cleaned, {name: rule for name, rule in template['fields'].items() if rule['read'] != 'jsonld'})
    rule = template['fields'].get('content')
    if rule and rule['read'] != 'jsonld':
        node = cleaned.select_one(rule['selector'])
        if node is not None and link_noise(node):
            raise ValueError('low_quality')
    if not any(rule['read'] == 'jsonld' for rule in template['fields'].values()):
        return values
    soup = bounded_document(body)
    entities = []
    for script in soup.select('script[type="application/ld+json"]'):
        doc = json.loads(script.string or script.get_text(), object_pairs_hook=_unique,
                         parse_constant=_invalid)
        stack, count = [(doc, 0)], 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if count > 4096 or depth > 32:
                raise ValueError('resource_limit')
            children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else ()
            stack.extend((child, depth + 1) for child in children)
        queue = list(doc) if isinstance(doc, list) else [doc]
        while queue:
            node = queue.pop(0)
            if not isinstance(node, dict):
                continue
            if isinstance(node.get('@graph'), list):
                queue.extend(node['@graph'])
            kinds = node.get('@type', [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if any(kind in template.get('jsonld_types', []) for kind in kinds):
                entities.append(node)
    matched = [node for node in entities if isinstance(node.get('url', node.get('@id')), str)
               and urldefrag(urljoin(url, node.get('url', node.get('@id'))))[0] == url]
    if not matched and len(entities) == 1 and not any(k in entities[0] for k in ('url', '@id')):
        matched = entities
    if len(matched) != 1:
        raise ValueError('invalid_article')
    if matched[0].get('isAccessibleForFree') in (False, 'false', 'False'):
        raise ValueError('paywall')
    for name, rule in template['fields'].items():
        if rule['read'] != 'jsonld':
            continue
        value = matched[0]
        for part in rule['path']:
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, str) and value.strip():
            values[name] = clean_content(value) if name == 'content' else value.strip()
    return values
