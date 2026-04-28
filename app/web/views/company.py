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

from app.models.sector_group import SectorGroup


def _get_sector_groups():
    """Get sector groups from DB. Falls back to empty dict if table is empty."""
    return SectorGroup.as_dict()


def _get_sector_group(sector: str) -> str:
    """Map a sector string to a visual group name using DB-stored keywords."""
    if not sector:
        return 'Other'
    # If the sector exactly matches a group name, use it directly
    groups = _get_sector_groups()
    if sector in groups:
        return sector
    sector_lower = sector.lower()
    for group_name, cfg in groups.items():
        if any(kw in sector_lower for kw in cfg.get('keywords', [])):
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
        # Sector-grouped map view: Grenoble companies with article counts (single query)
        grenoble_companies = Company.grenoble_with_counts()

        # Group by sector
        grouped = defaultdict(list)
        for c in grenoble_companies:
            group = _get_sector_group(c.sector)
            grouped[group].append(c)

        # Sort groups by DB order, then 'Other' last
        sector_groups = _get_sector_groups()
        ordered_groups = []
        for group_name in sector_groups:
            if group_name in grouped:
                ordered_groups.append((group_name, sector_groups[group_name], grouped[group_name]))
        if 'Other' in grouped:
            ordered_groups.append(('Uncategorized', {'icon': 'question-circle', 'color': '#94A3B8'}, grouped['Other']))

        return render_template(
            'company/index.html',
            view_mode='map',
            grouped=ordered_groups,
            search_query=search,
            sectors=sectors,
            current_sector=sector,
            grenoble_only=grenoble_only,
            sector_groups=sector_groups,
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

    # Sentiment stats (single aggregation query instead of 3)
    raw_stats = dict(
        db.session.query(
            ArticleCompany.sentiment,
            func.count(ArticleCompany.id)
        )
        .filter(ArticleCompany.company_id == company.id)
        .group_by(ArticleCompany.sentiment)
        .all()
    )
    sentiment_stats = {
        'positive': raw_stats.get('positive', 0),
        'neutral': raw_stats.get('neutral', 0),
        'negative': raw_stats.get('negative', 0),
    }

    trend_data = _get_sentiment_trend(company.id)

    return render_template(
        'company/detail.html',
        company=company,
        articles=articles,
        sentiment_stats=sentiment_stats,
        trend_data_json=json.dumps(trend_data),
        sector_group=_get_sector_group(company.sector),
        sector_config=_get_sector_groups().get(_get_sector_group(company.sector), {}),
        sector_groups=list(_get_sector_groups().keys()),
    )


@company_bp.route('/<slug>/update-sector', methods=['POST'])
@login_required
def update_sector(slug):
    """Update company sector group (admin only)."""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('company.detail', slug=slug))
    company = Company.query.filter_by(slug=slug).first_or_404()
    new_sector = request.form.get('sector', '').strip()
    if new_sector:
        company.sector = new_sector
        db.session.commit()
        flash(f'Sector updated to "{new_sector}".', 'success')
    return redirect(url_for('company.detail', slug=slug))


@company_bp.route('/<slug>/generate-analysis', methods=['POST'])
@login_required
def generate_analysis(slug):
    """Refresh AI analysis: crawl company website + recent news, merge non-empty fields."""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('company.detail', slug=slug))

    company = Company.query.filter_by(slug=slug).first_or_404()

    # 1. Try to crawl the company's homepage. ai_analysis['website'] is the
    #    LLM-detected (and admin-editable) real homepage and takes priority;
    #    company.website is often the discovery source (e.g. a directory listing)
    #    and is used as a fallback only.
    from app.utils.website_fetcher import fetch_website_excerpt

    site_url = None
    if isinstance(company.ai_analysis, dict):
        site_url = (company.ai_analysis.get('website') or '').strip() or None
    if not site_url:
        site_url = company.website

    website_excerpt, fetch_status = (None, 'no_url')
    if site_url:
        website_excerpt, fetch_status = fetch_website_excerpt(site_url)

    # 2. Gather recent news about this company.
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
        from app.llm.tasks import _save_revision

        client = LLMClient()
        analysis = client.analyze_company(
            name=company.name,
            sector=company.sector,
            headquarters=company.headquarters,
            description=company.description,
            spinoff_origin=company.spinoff_origin,
            company_stage=company.company_stage,
            recent_news=recent_news,
            website_excerpt=website_excerpt,
        )

        # 3. Merge: only overwrite fields where the LLM produced a non-empty value.
        old = company.ai_analysis if isinstance(company.ai_analysis, dict) else {}
        merged = dict(old)
        for key, val in analysis.items():
            if key == 'competitors':
                # The competitors table is replaced wholesale only if the new list is non-empty.
                if isinstance(val, list) and val:
                    merged['competitors'] = val
                continue
            if val not in (None, '', []):
                merged[key] = val

        # 4. Record revision (field-level diff vs. old) and persist.
        revision_source = {
            'ok': 'ai-refresh-website',
            'too_thin': 'ai-refresh-news',
            'http_error': 'ai-refresh-news',
            'fetch_error': 'ai-refresh-news',
            'no_url': 'ai-refresh-news',
        }.get(fetch_status, 'ai-refresh-news')
        revision_trigger = {
            'ok': f'Crawled {site_url}',
            'too_thin': f'{site_url} returned too little text (likely SPA)',
            'http_error': f'{site_url} returned non-2xx',
            'fetch_error': f'{site_url} unreachable',
            'no_url': 'No website URL on record',
        }.get(fetch_status, '')

        _save_revision(company, new_data=merged, source=revision_source, trigger=revision_trigger)
        company.ai_analysis = merged
        company.ai_analysis_at = datetime.utcnow()
        db.session.commit()

        if fetch_status == 'ok':
            flash(f'Refreshed {company.name} from website + news.', 'success')
        else:
            flash(
                f'Refreshed {company.name} from news only ({fetch_status} on {site_url or "no URL"}).',
                'warning'
            )
    except Exception as e:
        flash(f'Analysis failed: {e}', 'error')

    return redirect(url_for('company.detail', slug=slug))


@company_bp.route('/<slug>/edit-analysis', methods=['GET', 'POST'])
@login_required
def edit_analysis(slug):
    """Manually edit structured AI analysis fields (admin only)."""
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('company.detail', slug=slug))

    company = Company.query.filter_by(slug=slug).first_or_404()

    if request.method == 'POST':
        from app.llm.tasks import _save_revision

        new_data = {
            'website': request.form.get('website', '').strip(),
            'overview': request.form.get('overview', '').strip(),
            'founders': request.form.get('founders', '').strip(),
            'spinoff_source': request.form.get('spinoff_source', '').strip(),
            'core_tech': request.form.get('core_tech', '').strip(),
            'cn_competitor_names': request.form.get('cn_competitor_names', '').strip(),
            'competitors': [],
            'business_status': request.form.get('business_status', '').strip(),
            'recommendation': request.form.get('recommendation', '').strip(),
            'recommendation_reason': request.form.get('recommendation_reason', '').strip(),
        }
        # Parse competitors table from form
        dims = request.form.getlist('comp_dimension')
        comps = request.form.getlist('comp_company')
        cns = request.form.getlist('comp_cn')
        for d, c, cn in zip(dims, comps, cns):
            if d.strip():
                new_data['competitors'].append({
                    'dimension': d.strip(),
                    'company': c.strip(),
                    'cn_competitor': cn.strip(),
                })

        _save_revision(company, new_data=new_data, source='manual-edit', trigger='Admin manual edit')
        company.ai_analysis = new_data
        company.ai_analysis_at = datetime.utcnow()
        db.session.commit()
        flash(f'Analysis for {company.name} updated.', 'success')
        return redirect(url_for('company.detail', slug=slug))

    return render_template(
        'company/edit_analysis.html',
        company=company,
        data=company.ai_analysis if isinstance(company.ai_analysis, dict) else {},
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
        'labels': weeks[-12:],
        'positive': pos[-12:],
        'neutral': neu[-12:],
        'negative': neg[-12:],
    }
