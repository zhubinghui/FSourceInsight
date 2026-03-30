"""Clean HTML tags from all article content in the database.

Run once to fix existing articles that were crawled before HTML stripping was added.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.article import Article
from app.utils.text import strip_html


def main():
    app = create_app()
    with app.app_context():
        articles = Article.query.all()
        cleaned = 0

        for article in articles:
            changed = False
            for field in [
                'title_fr', 'title_zh', 'title_en',
                'content_fr', 'content_zh', 'content_en',
                'summary_fr', 'summary_zh', 'summary_en',
            ]:
                val = getattr(article, field)
                if val and ('<' in val or '&' in val):
                    new_val = strip_html(val)
                    if new_val != val:
                        setattr(article, field, new_val)
                        changed = True

            if changed:
                cleaned += 1

        db.session.commit()
        print(f'Cleaned HTML from {cleaned}/{len(articles)} articles.')


if __name__ == '__main__':
    main()
