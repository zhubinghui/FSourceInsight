import logging
from datetime import datetime, timedelta

from app.extensions import db
from app.models.article import Article
from app.models.user import User, KeywordSubscription
from app.models.category import Category

logger = logging.getLogger(__name__)

# Priority weights for highlight types (higher = more important)
HIGHLIGHT_PRIORITY = {
    'tech_breakthrough': 4,
    'local_research': 3,
    'investment': 2,
    'local_event': 1,
}


def _highlight_score(article):
    """Compute max highlight priority score for an article."""
    if not article.highlights:
        return 0
    return max(HIGHLIGHT_PRIORITY.get(h, 0) for h in article.highlights)


def build_daily_digest(user: User) -> dict | None:
    """Build a daily digest for a user. Returns None if no articles to send.

    Articles are split into two groups:
    - top_insights: highlighted articles sorted by priority weight
    - articles: remaining articles by recency
    """
    since = datetime.utcnow() - timedelta(hours=24)
    lang = user.preferred_language or 'zh'

    all_articles = (
        Article.query
        .filter(Article.crawled_at >= since)
        .order_by(Article.published_at.desc())
        .all()
    )

    if not all_articles:
        return None

    def get_localized(article, field):
        val = getattr(article, f'{field}_{lang}', None)
        if val:
            return val
        return getattr(article, f'{field}_fr', '') or ''

    def to_item(article):
        return {
            'id': article.id,
            'title': get_localized(article, 'title'),
            'summary': get_localized(article, 'summary'),
            'url': article.url,
            'source': article.source.name if article.source else '',
            'published_at': article.published_at,
            'highlights': article.highlights or [],
        }

    # Split into highlighted (top insights) and regular articles
    top_insights = []
    regular = []
    for article in all_articles:
        if article.highlights and _highlight_score(article) > 0:
            top_insights.append(article)
        else:
            regular.append(article)

    # Sort top insights by priority (highest first), then recency
    top_insights.sort(
        key=lambda a: (-_highlight_score(a), -(a.published_at.timestamp() if a.published_at else 0))
    )

    return {
        'user': user,
        'top_insights': [to_item(a) for a in top_insights],
        'articles': [to_item(a) for a in regular],
        'article_count': len(all_articles),
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
