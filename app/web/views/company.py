import json
from collections import defaultdict

from flask import Blueprint, render_template, request
from sqlalchemy import func, extract

from app.extensions import db
from app.models.company import Company
from app.models.article import Article, ArticleCompany

company_bp = Blueprint('company', __name__)


@company_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    sector = request.args.get('sector', '').strip()
    grenoble_only = request.args.get('grenoble') == '1'

    query = Company.query
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(Company.name.like(like), Company.sector.like(like)))
    if sector:
        query = query.filter(Company.sector == sector)
    if grenoble_only:
        query = query.filter(Company.is_grenoble == True)

    companies = query.order_by(Company.name).paginate(page=page, per_page=30, error_out=False)

    # Get distinct sectors for filter
    sectors = [
        r[0] for r in
        db.session.query(Company.sector).filter(Company.sector.isnot(None)).distinct().order_by(Company.sector).all()
    ]

    # HTMX partial
    if request.headers.get('HX-Request'):
        return render_template('company/_company_grid.html', companies=companies)

    return render_template(
        'company/index.html',
        companies=companies,
        search_query=search,
        sectors=sectors,
        current_sector=sector,
        grenoble_only=grenoble_only,
    )


@company_bp.route('/search')
def search():
    """HTMX live search endpoint."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    sector = request.args.get('sector', '').strip()
    grenoble_only = request.args.get('grenoble') == '1'

    query = Company.query
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(Company.name.like(like), Company.sector.like(like)))
    if sector:
        query = query.filter(Company.sector == sector)
    if grenoble_only:
        query = query.filter(Company.is_grenoble == True)

    companies = query.order_by(Company.name).paginate(page=page, per_page=30, error_out=False)
    return render_template('company/_company_grid.html', companies=companies)


@company_bp.route('/<slug>')
def detail(slug):
    company = Company.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)

    articles = (
        Article.query
        .join(ArticleCompany)
        .filter(ArticleCompany.company_id == company.id)
        .order_by(Article.published_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )

    # Sentiment stats
    sentiment_stats = {
        'positive': ArticleCompany.query.filter_by(
            company_id=company.id, sentiment='positive'
        ).count(),
        'neutral': ArticleCompany.query.filter_by(
            company_id=company.id, sentiment='neutral'
        ).count(),
        'negative': ArticleCompany.query.filter_by(
            company_id=company.id, sentiment='negative'
        ).count(),
    }

    # Sentiment trend data for Chart.js (last 30 days, grouped by week)
    trend_data = _get_sentiment_trend(company.id)

    return render_template(
        'company/detail.html',
        company=company,
        articles=articles,
        sentiment_stats=sentiment_stats,
        trend_data_json=json.dumps(trend_data),
    )


def _get_sentiment_trend(company_id: int) -> dict:
    """Build sentiment trend data grouped by week for Chart.js."""
    rows = (
        db.session.query(
            func.yearweek(Article.published_at).label('yw'),
            func.min(Article.published_at).label('week_start'),
            ArticleCompany.sentiment,
            func.count(ArticleCompany.id).label('cnt'),
        )
        .join(Article, ArticleCompany.article_id == Article.id)
        .filter(ArticleCompany.company_id == company_id)
        .filter(Article.published_at.isnot(None))
        .group_by('yw', ArticleCompany.sentiment)
        .order_by('yw')
        .all()
    )

    weeks = []
    pos = []
    neu = []
    neg = []
    week_map = defaultdict(lambda: {'positive': 0, 'neutral': 0, 'negative': 0})

    for row in rows:
        label = row.week_start.strftime('%m/%d') if row.week_start else str(row.yw)
        week_map[label][row.sentiment] = row.cnt

    for label in sorted(week_map.keys()):
        weeks.append(label)
        pos.append(week_map[label]['positive'])
        neu.append(week_map[label]['neutral'])
        neg.append(week_map[label]['negative'])

    return {
        'labels': weeks[-12:],  # Last 12 weeks
        'positive': pos[-12:],
        'neutral': neu[-12:],
        'negative': neg[-12:],
    }
