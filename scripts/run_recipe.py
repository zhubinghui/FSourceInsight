"""Manual recipe preview/apply. Never publishes configuration or dispatches LLM work."""
import argparse
import base64
from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawlers.contracts import FetchObservation
from app.crawlers.engine import CrawlEngine, PageSnapshot, QualityProfile
from app.crawlers.fetcher import FetchPolicy, FetchResponse
from app.crawlers.schema import validate_recipe


def load_snapshots(path, source_id):
    with open(path, 'rb') as stream:
        raw = stream.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError('Invalid snapshots')
    doc = json.loads(raw)
    if doc['format_version'] != 1 or doc['source_id'] != source_id or len(doc['pages']) > 16:
        raise ValueError('Invalid snapshots')
    pages = []
    for value in doc['pages']:
        observation = dict(value['observation'])
        observation['fetched_at'] = datetime.fromisoformat(observation['fetched_at'])
        if observation['error'] is not None:
            raise ValueError('Invalid snapshots')
        body = base64.b64decode(value['body'], validate=True)
        pages.append(PageSnapshot(value['url'], FetchResponse(observation=FetchObservation(**observation),
                                   body=body, document_url=value['document_url'])))
    return tuple(pages)


def save_snapshots(path, source_id, pages, profile):
    values = []
    for page in pages:
        observation = asdict(page.response.observation)
        observation['fetched_at'] = page.response.observation.fetched_at.isoformat()
        values.append({'url': page.url, 'document_url': page.response.document_url,
                       'body': base64.b64encode(page.response.body).decode(), 'observation': observation})
    payload = json.dumps({'format_version': 1, 'source_id': source_id, 'pages': values,
                          'captured_engine': CrawlEngine.VERSION, 'captured_quality_profile': asdict(profile)}).encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', required=True)
    parser.add_argument('--allow-host', action='append', required=True, help='Explicit trusted network host; repeat for each host')
    parser.add_argument('--profile', choices=['news', 'bulletin'], default='news', help='Trusted system quality profile, not supplied by recipe/snapshot')
    parser.add_argument('--apply', action='store_true', help='Apply this operator-selected recipe once; not active-schema publication')
    parser.add_argument('--save-snapshots', help='Create a private NEW file containing raw bodies and exact URLs; sensitive')
    parser.add_argument('--replay', help='Preview-only local snapshots; missing pages never fetch')
    args = parser.parse_args()
    if args.apply and (args.replay or args.save_snapshots):
        parser.error('Apply cannot be combined with snapshot replay/save')
    try:
        with open(args.recipe, 'rb') as stream:
            recipe = validate_recipe(stream.read(65537).decode('utf-8'))
        source_id = recipe.to_dict()['source_id']
        snapshots = load_snapshots(args.replay, source_id) if args.replay else None
        profile = QualityProfile(min_content_chars=80, min_paragraphs=1) if args.profile == 'bulletin' else QualityProfile()
        engine = CrawlEngine(source_id, recipe=recipe, fetch_policy=FetchPolicy(allowed_hosts=tuple(args.allow_host)), snapshots=snapshots, profile=profile)
        if args.apply:
            from app import create_app
            from flask import has_app_context
            if has_app_context():
                result = engine.run()
            else:
                with create_app().app_context():
                    result = engine.run()
        else:
            result = engine.preview()
            if args.save_snapshots:
                save_snapshots(args.save_snapshots, source_id, result.snapshots, profile)
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        parser.error('Invalid recipe, policy, source or snapshot input/output')
    output = {'status': result.status, 'recipe': recipe.fingerprint, 'engine': engine.VERSION,
              'quality_profile': asdict(profile), 'quality': asdict(result.quality),
              'errors': [e.code for e in result.errors], 'article_ids': list(getattr(result, 'article_ids', ()))}
    if not args.apply:
        output['content_levels'] = dict(Counter(a.content_level for a in result.articles))
    print(json.dumps(output, ensure_ascii=False))
    return 0 if result.status in {'ready', 'success', 'no_change'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
