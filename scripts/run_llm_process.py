"""Manually trigger LLM processing for unprocessed articles."""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.article import Article
from app.llm.client import LLMClient
from app.llm.tasks import _link_companies, _link_categories


def main():
    parser = argparse.ArgumentParser(description='Run LLM processing manually')
    parser.add_argument('--limit', '-n', type=int, default=10,
                        help='Max articles to process (default: 10)')
    parser.add_argument('--article-id', '-a', type=int,
                        help='Process a specific article by ID')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Force reprocess even if already processed')
    parser.add_argument('--skip-translate', action='store_true',
                        help='Skip translation step')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without doing it')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.article_id:
            articles = [db.session.get(Article, args.article_id)]
            if not articles[0]:
                print(f'Article {args.article_id} not found')
                return
        else:
            query = Article.query
            if not args.force:
                query = query.filter_by(llm_processed=False)
            articles = (
                query.order_by(Article.crawled_at.desc())
                .limit(args.limit)
                .all()
            )

        if not articles:
            print('No unprocessed articles found.')
            return

        print(f'Processing {len(articles)} article(s)...\n')

        if args.dry_run:
            for a in articles:
                print(f'  [{a.id}] {a.title_fr[:80]}')
            print(f'\nDry run — {len(articles)} articles would be processed.')
            return

        client = LLMClient()
        success = 0
        failed = 0

        for article in articles:
            print(f'\n--- Article {article.id}: {article.title_fr[:60]} ---')
            text = article.content_fr or article.title_fr

            try:
                # Clear old associations if reprocessing
                if article.llm_processed or args.force:
                    from app.models.article import ArticleCompany, ArticleCategory
                    ArticleCompany.query.filter_by(article_id=article.id).delete()
                    ArticleCategory.query.filter_by(article_id=article.id).delete()
                    db.session.flush()

                # Translate title + Digest content
                if not args.skip_translate:
                    print('  Translating title...')
                    article.title_zh = client.translate(article.title_fr, 'zh', article.id)
                    article.title_en = client.translate(article.title_fr, 'en', article.id)
                    if article.content_fr:
                        print('  Digesting content...')
                        article.content_zh = client.digest(
                            article.title_fr, article.content_fr, 'zh', article.id
                        )
                        article.content_en = client.digest(
                            article.title_fr, article.content_fr, 'en', article.id
                        )

                # Summarize
                print('  Summarizing...')
                article.summary_fr = client.summarize(text, 'fr', article.id)
                article.summary_zh = client.summarize(text, 'zh', article.id)
                article.summary_en = client.summarize(text, 'en', article.id)

                # NER
                print('  Extracting companies...')
                companies = client.extract_companies(text, article.id)
                print(f'    Found: {[c.get("name") for c in companies]}')
                _link_companies(article, companies, client, text)

                # Classify + highlights
                print('  Classifying...')
                classify_result = client.classify_category(text, article.id)
                print(f'    Categories: {[c.get("category") for c in classify_result["categories"]]}')
                if classify_result['highlights']:
                    print(f'    Highlights: {classify_result["highlights"]}')
                _link_categories(article, classify_result['categories'])
                article.highlights = classify_result['highlights'] or None
                if classify_result.get('event_date'):
                    try:
                        from datetime import date
                        article.event_date = date.fromisoformat(classify_result['event_date'])
                        print(f'    Event date: {article.event_date}')
                    except (ValueError, TypeError):
                        pass

                # Strategic insight
                print('  Generating insight...')
                article.insight_zh = client.generate_insight(
                    article.title_fr, text, 'zh', article.id
                )
                article.insight_en = client.generate_insight(
                    article.title_fr, text, 'en', article.id
                )
                print('    Insight generated.')

                # Mark done with provider/model info
                from datetime import datetime
                config = client._get_config('translate') or client._get_config('summarize')
                article.llm_processed = True
                article.llm_processed_at = datetime.utcnow()
                if config:
                    article.llm_provider = config.provider
                    article.llm_model = config.model
                db.session.commit()
                success += 1
                print('  Done.')

            except Exception as e:
                failed += 1
                print(f'  FAILED: {e}')
                db.session.rollback()

        print(f'\n\nResults: {success} success, {failed} failed')


if __name__ == '__main__':
    main()
