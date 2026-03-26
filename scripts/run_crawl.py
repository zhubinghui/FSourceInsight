"""Manually trigger a crawl for all active sources or a specific source."""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.source import NewsSource
from app.crawlers.registry import get_crawler, discover_crawlers


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

        print(f'Crawling {len(sources)} source(s)...\n')
        for source in sources:
            print(f'--- {source.name} ({source.feed_type}) ---')
            try:
                crawler = get_crawler(source)
                result = crawler.run()
                print(f'  Found: {result.articles_found}, New: {result.articles_new}')
                if result.errors:
                    for err in result.errors:
                        print(f'  Error: {err}')
            except Exception as e:
                print(f'  FAILED: {e}')
            print()


if __name__ == '__main__':
    main()
