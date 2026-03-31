from datetime import datetime, timedelta

from flask import Blueprint, render_template, request
from app.extensions import db
from app.models.article import Article, ArticleCompany
from app.models.source import NewsSource
from app.models.category import Category
from app.models.company import Company

news_bp = Blueprint('news', __name__)

# Priority weights for highlight types (higher = more important)
HIGHLIGHT_PRIORITY = {
    'tech_breakthrough': 4,
    'local_research': 3,
    'investment': 2,
    'local_event': 1,
}


def _highlight_score(article):
    """Compute max highlight priority score for sorting."""
    if not article.highlights:
        return 0
    return max(HIGHLIGHT_PRIORITY.get(h, 0) for h in article.highlights)


def _build_article_query():
    """Build filtered article query from request args."""
    query = Article.query.order_by(Article.published_at.desc())

    source_id = request.args.get('source_id', type=int)
    category_id = request.args.get('category_id', type=int)
    company_id = request.args.get('company_id', type=int)
    search = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    if source_id:
        query = query.filter_by(source_id=source_id)
    if category_id:
        query = query.filter(Article.categories.any(id=category_id))
    if company_id:
        query = query.join(ArticleCompany).filter(ArticleCompany.company_id == company_id)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Article.title_fr.like(like),
                Article.title_zh.like(like),
                Article.title_en.like(like),
                Article.content_fr.like(like),
            )
        )
    if date_from:
        try:
            query = query.filter(Article.published_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Article.published_at <= datetime.strptime(date_to, '%Y-%m-%d'))
        except ValueError:
            pass

    # Highlight filter
    highlight = request.args.get('highlight', '').strip()
    if highlight:
        query = query.filter(Article.highlights.like(f'%"{highlight}"%'))

    return query


def _get_filter_options():
    """Get dropdown options for filters."""
    return {
        'sources': NewsSource.query.filter_by(is_active=True).order_by(NewsSource.name).all(),
        'categories': Category.query.order_by(Category.name).all(),
        'companies': Company.query.order_by(Company.name).all(),
    }


def _get_highlighted_articles(page=1, per_page=5):
    """Get highlighted articles sorted by priority weight, paginated.

    Priority: tech_breakthrough (4) > local_research (3) > investment (2) > local_event (1)
    Time windows are configurable via Admin > Settings (system_setting table).
    Returns (items, total) for pagination.
    """
    from app.models.setting import SystemSetting

    now = datetime.now()
    bt_days = SystemSetting.get_int('highlight_breakthrough_days', 7)
    rs_days = SystemSetting.get_int('highlight_research_days', 7)
    inv_days = SystemSetting.get_int('highlight_investment_days', 7)
    ev_days = SystemSetting.get_int('highlight_event_days', 14)

    # Each highlight type can have its own time window
    high_value_articles = []

    for hl_type, days in [
        ('tech_breakthrough', bt_days),
        ('local_research', rs_days),
        ('investment', inv_days),
    ]:
        cutoff = now - timedelta(days=days)
        articles = (
            Article.query
            .filter(Article.highlights.isnot(None))
            .filter(Article.highlights.like(f'%{hl_type}%'))
            .filter(Article.published_at >= cutoff)
            .all()
        )
        high_value_articles.extend(articles)

    # Events: future or within event_days fallback
    ev_cutoff = now - timedelta(days=ev_days)
    events = (
        Article.query
        .filter(Article.highlights.like('%local_event%'))
        .filter(
            db.or_(
                Article.event_date >= now.date(),
                db.and_(
                    Article.event_date.is_(None),
                    Article.published_at >= ev_cutoff,
                )
            )
        )
        .all()
    )

    # Merge, deduplicate, then sort by priority weight (highest first)
    seen = set()
    merged = []
    for a in high_value_articles + events:
        if a.id not in seen:
            seen.add(a.id)
            merged.append(a)

    merged.sort(key=lambda a: (-_highlight_score(a), -(a.published_at.timestamp() if a.published_at else 0)))

    # Manual pagination
    total = len(merged)
    start = (page - 1) * per_page
    items = merged[start:start + per_page]
    return items, total


@news_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = _build_article_query()
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    options = _get_filter_options()

    # Get highlighted articles for top section (when no text/highlight filter active)
    highlighted = []
    hl_total = 0
    hl_page = request.args.get('hl_page', 1, type=int)
    hl_per_page = 5
    if not request.args.get('q') and not request.args.get('highlight'):
        highlighted, hl_total = _get_highlighted_articles(page=hl_page, per_page=hl_per_page)

    # If HTMX request, return only the article list partial
    if request.headers.get('HX-Request'):
        return render_template(
            'news/_article_list.html',
            articles=pagination.items,
            pagination=pagination,
        )

    return render_template(
        'news/index.html',
        articles=pagination.items,
        pagination=pagination,
        **options,
        current_source_id=request.args.get('source_id', type=int),
        current_category_id=request.args.get('category_id', type=int),
        current_company_id=request.args.get('company_id', type=int),
        search_query=request.args.get('q', ''),
        date_from=request.args.get('date_from', ''),
        date_to=request.args.get('date_to', ''),
        current_highlight=request.args.get('highlight', ''),
        highlighted=highlighted,
        hl_page=hl_page,
        hl_total=hl_total,
        hl_pages=(hl_total + hl_per_page - 1) // hl_per_page if hl_total else 0,
    )


@news_bp.route('/top')
def top_insights():
    """Concise daily top insights page — only highest-value articles."""
    now = datetime.now()
    cutoff = now - timedelta(days=3)

    articles = (
        Article.query
        .filter(Article.highlights.isnot(None))
        .filter(Article.highlights != '[]')
        .filter(Article.published_at >= cutoff)
        .all()
    )

    # Filter to only articles with scored highlights and sort by priority
    scored = [(a, _highlight_score(a)) for a in articles if _highlight_score(a) > 0]
    scored.sort(key=lambda x: (-x[1], -(x[0].published_at.timestamp() if x[0].published_at else 0)))

    top = [a for a, _ in scored[:15]]

    return render_template('news/top_insights.html', articles=top)


@news_bp.route('/news/<int:article_id>')
def detail(article_id):
    article = Article.query.get_or_404(article_id)
    related_companies = article.companies.all()
    return render_template(
        'news/detail.html',
        article=article,
        related_companies=related_companies,
    )


@news_bp.route('/search')
def search():
    """HTMX endpoint for live search — returns article list partial."""
    page = request.args.get('page', 1, type=int)
    query = _build_article_query()
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    return render_template(
        'news/_article_list.html',
        articles=pagination.items,
        pagination=pagination,
    )
