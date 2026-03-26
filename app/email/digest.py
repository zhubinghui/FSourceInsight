import logging
from datetime import datetime, timedelta

from app.extensions import db
from app.models.article import Article
from app.models.user import User, KeywordSubscription
from app.models.category import Category

logger = logging.getLogger(__name__)


def build_daily_digest(user: User) -> dict | None:
    """Build a daily digest for a user. Returns None if no articles to send."""
    since = datetime.utcnow() - timedelta(hours=24)
    lang = user.preferred_language or 'zh'

    articles = (
        Article.query
        .filter(Article.crawled_at >= since)
        .order_by(Article.published_at.desc())
        .all()
    )

    if not articles:
        return None

    # Get title and summary in preferred language
    def get_localized(article, field):
        val = getattr(article, f'{field}_{lang}', None)
        if val:
            return val
        return getattr(article, f'{field}_fr', '') or ''

    items = []
    for article in articles:
        items.append({
            'id': article.id,
            'title': get_localized(article, 'title'),
            'summary': get_localized(article, 'summary'),
            'url': article.url,
            'source': article.source.name if article.source else '',
            'published_at': article.published_at,
        })

    return {
        'user': user,
        'articles': items,
        'article_count': len(items),
        'date': datetime.utcnow().strftime('%Y-%m-%d'),
    }


def find_keyword_matches(user: User) -> list[dict]:
    """Find articles matching user's keyword subscriptions from last 24h."""
    since = datetime.utcnow() - timedelta(hours=24)
    lang = user.preferred_language or 'zh'

    active_subs = user.subscriptions.filter_by(is_active=True).all()
    if not active_subs:
        return []

    matched_articles = []
    for sub in active_subs:
        keyword = sub.keyword
        articles = (
            Article.query
            .filter(
                Article.crawled_at >= since,
                db.or_(
                    Article.title_fr.contains(keyword),
                    Article.content_fr.contains(keyword),
                    Article.title_zh.contains(keyword),
                    Article.title_en.contains(keyword),
                )
            )
            .order_by(Article.published_at.desc())
            .all()
        )

        for article in articles:
            title = getattr(article, f'title_{lang}', None) or article.title_fr
            summary = getattr(article, f'summary_{lang}', None) or article.summary_fr or ''
            matched_articles.append({
                'id': article.id,
                'title': title,
                'summary': summary,
                'url': article.url,
                'keyword': keyword,
                'source': article.source.name if article.source else '',
                'published_at': article.published_at,
            })

    # Deduplicate by article id
    seen = set()
    unique = []
    for item in matched_articles:
        if item['id'] not in seen:
            seen.add(item['id'])
            unique.append(item)

    return unique
