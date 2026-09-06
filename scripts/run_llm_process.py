"""Manually process articles using the same atomic pipeline as Celery."""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.article import Article
from app.llm.pipeline import process_article


def main():
    parser = argparse.ArgumentParser(description='Run LLM processing manually')
    parser.add_argument('--limit', '-n', type=int, default=10,
                        help='Max articles to process (default: 10)')
    parser.add_argument('--article-id', '-a', type=int, help='Process a specific article by ID')
    parser.add_argument('--force', '-f', action='store_true', help='Reprocess an already processed article')
    parser.add_argument('--skip-translate', action='store_true', help='Skip translation and digest')
    parser.add_argument('--dry-run', action='store_true', help='Show work without making model calls')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.article_id:
            article = db.session.get(Article, args.article_id)
            if not article:
                print(f'Article {args.article_id} not found')
                return
            articles = [article]
        else:
            query = Article.query
            if not args.force:
                query = query.filter_by(llm_processed=False)
            articles = query.order_by(Article.crawled_at.desc()).limit(args.limit).all()
        work = [(a.id, a.title_fr) for a in articles]
        db.session.remove()  # Never hold a business transaction across paid calls.
        if not work:
            print('No unprocessed articles found.')
            return
        print(f'Processing {len(work)} article(s)...\n')
        if args.dry_run:
            for article_id, title in work:
                print(f'  [{article_id}] {title[:80]}')
            print(f'\nDry run — {len(work)} articles would be processed.')
            return
        success = failed = skipped = 0
        for article_id, title in work:
            print(f'\n--- Article {article_id}: {title[:60]} ---')
            try:
                if process_article(article_id, force=args.force, skip_translate=args.skip_translate):
                    success += 1
                    print('  Done.')
                else:
                    skipped += 1
                    print('  Skipped (missing or already processed).')
            except Exception as exc:
                failed += 1
                print(f'  FAILED: {exc}')
        print(f'\nResults: {success} success, {failed} failed, {skipped} skipped')


if __name__ == '__main__':
    main()
