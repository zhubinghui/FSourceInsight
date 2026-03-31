import json
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, extract

from app.extensions import db
from app.models.company import Company
from app.models.article import Article, ArticleCompany

company_bp = Blueprint('company', __name__)

# Sector group mapping: normalize fine-grained sectors into visual groups
SECTOR_GROUPS = {
    'Semiconductor': {
        'icon': 'cpu',
        'color': '#2563EB',
        'keywords': ['semiconductor', 'chip', 'wafer', 'mems', 'ic design', 'fabricat'],
    },
    'AI & Computing': {
        'icon': 'robot',
        'color': '#7C3AED',
        'keywords': ['ai', 'machine learning', 'computing', 'processor', 'neuromorphic', 'quantum', 'digital system'],
    },
    'Photonics & Sensors': {
        'icon': 'eye',
        'color': '#0891B2',
        'keywords': ['photonic', 'sensor', 'lidar', 'infrared', 'optic', 'vision', 'display', 'oled', 'micro-led', 'led'],
    },
    'MedTech & Health': {
        'icon': 'heart-pulse',
        'color': '#DC2626',
        'keywords': ['medtech', 'health', 'biotech', 'medical', 'diagnostic', 'pharma', 'implant'],
    },
    'Energy & CleanTech': {
        'icon': 'lightning-charge',
        'color': '#059669',
        'keywords': ['energy', 'cleantech', 'power', 'battery', 'climat'],
    },
    'IoT & Connectivity': {
        'icon': 'wifi',
        'color': '#F97316',
        'keywords': ['iot', 'connected', 'rfid', 'smart city', 'telecom'],
    },
    'Software & Digital': {
        'icon': 'code-slash',
        'color': '#6366F1',
        'keywords': ['software', 'saas', 'digital', 'fintech', 'cyber', 'data'],
    },
    'Research & Ecosystem': {
        'icon': 'mortarboard',
        'color': '#64748B',
        'keywords': ['research', 'university', 'cluster', 'incubator', 'transfer', 'facilit'],
    },
}


def _get_sector_group(sector: str) -> str:
    """Map a fine-grained sector string to a visual group name."""
    if not sector:
        return 'Other'
    sector_lower = sector.lower()
    for group_name, cfg in SECTOR_GROUPS.items():
        if any(kw in sector_lower for kw in cfg['keywords']):
            return group_name
    return 'Other'


@company_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    sector = request.args.get('sector', '').strip()
    grenoble_only = request.args.get('grenoble') == '1'
    view_mode = request.args.get('view', 'map')  # 'map' or 'list'

    query = Company.query
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(Company.name.like(like), Company.sector.like(like)))
    if sector:
        query = query.filter(Company.sector == sector)
    if grenoble_only:
        query = query.filter(Company.is_grenoble == True)

    # Get distinct sectors for filter
    sectors = [
        r[0] for r in
        db.session.query(Company.sector).filter(Company.sector.isnot(None)).distinct().order_by(Company.sector).all()
    ]

    if view_mode == 'map' and not search and not sector:
        # Sector-grouped map view: only Grenoble companies with articles
        grenoble_companies = (
            Company.query
            .filter(Company.is_grenoble == True)
            .order_by(Company.name)
            .all()
        )

        # Group by sector
        grouped = defaultdict(list)
        for c in grenoble_companies:
            group = _get_sector_group(c.sector)
            grouped[group].append(c)

        # Sort groups by SECTOR_GROUPS order, then 'Other' last
        ordered_groups = []
        for group_name in SECTOR_GROUPS:
            if group_name in grouped:
                ordered_groups.append((group_name, SECTOR_GROUPS[group_name], grouped[group_name]))
        if 'Other' in grouped:
            ordered_groups.append(('Other', {'icon': 'grid', 'color': '#94A3B8'}, grouped['Other']))

        return render_template(
            'company/index.html',
            view_mode='map',
            grouped=ordered_groups,
            search_query=search,
            sectors=sectors,
            current_sector=sector,
            grenoble_only=grenoble_only,
            sector_groups=SECTOR_GROUPS,
        )
    else:
        # List view (with search/filter/pagination)
        companies = query.order_by(Company.name).paginate(page=page, per_page=30, error_out=False)

        if request.headers.get('HX-Request'):
            return render_template('company/_company_grid.html', companies=companies)

        return render_template(
            'company/index.html',
            view_mode='list',
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
        'positive': ArticleCompany.query.filter_by(company_id=company.id, sentiment='positive').count(),
        'neutral': ArticleCompany.query.filter_by(company_id=company.id, sentiment='neutral').count(),
        'negative': ArticleCompany.query.filter_by(company_id=company.id, sentiment='negative').count(),
    }

    trend_data = _get_sentiment_trend(company.id)

    return render_template(
        'company/detail.html',
        company=company,
        articles=articles,
        sentiment_stats=sentiment_stats,
        trend_data_json=json.dumps(trend_data),
        sector_group=_get_sector_group(company.sector),
        sector_config=SECTOR_GROUPS.get(_get_sector_group(company.sector), {}),
    )


@company_bp.route('/<slug>/generate-analysis', methods=['POST'])
@login_required
def generate_analysis(slug):
    """Generate AI analysis for a company (admin only)."""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('company.detail', slug=slug))

    company = Company.query.filter_by(slug=slug).first_or_404()

    # Gather recent news about this company
    recent_articles = (
        Article.query
        .join(ArticleCompany)
        .filter(ArticleCompany.company_id == company.id)
        .order_by(Article.published_at.desc())
        .limit(5)
        .all()
    )
    recent_news = '\n'.join([
        f'- {a.title_fr or a.title_en or ""}'
        for a in recent_articles
    ]) if recent_articles else ''

    try:
        from app.llm.client import LLMClient
        client = LLMClient()
        analysis = client.analyze_company(
            name=company.name,
            sector=company.sector,
            headquarters=company.headquarters,
            description=company.description,
            spinoff_origin=company.spinoff_origin,
            company_stage=company.company_stage,
            recent_news=recent_news,
        )
        company.ai_analysis = analysis
        company.ai_analysis_at = datetime.utcnow()
        db.session.commit()
        flash(f'AI analysis generated for {company.name}.', 'success')
    except Exception as e:
        flash(f'Analysis failed: {e}', 'error')

    return redirect(url_for('company.detail', slug=slug))


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
        'labels': weeks[-12:],
        'positive': pos[-12:],
        'neutral': neu[-12:],
        'negative': neg[-12:],
    }
