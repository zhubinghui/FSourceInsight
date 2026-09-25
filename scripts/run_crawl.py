"""Manually crawl all active sources or one source, under the same claims as scheduled crawls."""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.source import NewsSource
from app.crawlers.registry import discover_crawlers


def main():
    parser = argparse.ArgumentParser(description='Run news crawlers manually')
    parser.add_argument('--source', '-s', help='Source slug to crawl (default: all active)')
    parser.add_argument('--list', '-l', action='store_true', help='List all sources')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        discover_crawlers()

        if args.list:
            sources = NewsSource.query.order_by(NewsSource.name).all()
            for s in sources:
                status = 'active' if s.is_active else 'inactive'
                print(f'  [{status}] {s.slug}: {s.name} ({s.feed_type})')
            return

        if args.source:
            sources = [NewsSource.query.filter_by(slug=args.source).first()]
            if not sources[0]:
                print(f'Source "{args.source}" not found')
                return
        else:
            sources = NewsSource.query.filter_by(is_active=True).all()

        from app.crawlers import runs, schedule
        runs.ensure_states(schedule.now())
        print(f'Crawling {len(sources)} source(s)...\n')
        for source in sources:
            print(f'--- {source.name} ({source.feed_type}) ---')
            claim = runs.claim(source.id, due_only=False)
            if claim is None:
                print('  Skipped: disabled, paused or already running')
                continue
            result = runs.execute(source.id, claim.claim_id)
            print(f'  Status: {getattr(result, "status", "not run")}')
            print()


if __name__ == '__main__':
    main()
