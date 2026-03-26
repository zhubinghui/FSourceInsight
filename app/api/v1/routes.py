"""REST API v1 for programmatic access to news and companies."""
from datetime import datetime

from flask import Blueprint, jsonify, request
from app.extensions import db
from app.models.article import Article, ArticleCompany
from app.models.company import Company
from app.models.source import NewsSource

api_bp = Blueprint('api', __name__)


@api_bp.route('/news')
def list_news():
    """List articles with pagination and filtering.

    Query params: page, per_page, source_id, company_id, q, date_from, date_to
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    source_id = request.args.get('source_id', type=int)
    company_id = request.args.get('company_id', type=int)
    search = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    query = Article.query.order_by(Article.published_at.desc())

    if source_id:
        query = query.filter_by(source_id=source_id)
    if company_id:
        query = query.join(ArticleCompany).filter(ArticleCompany.company_id == company_id)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(Article.title_fr.like(like), Article.title_zh.like(like))
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

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
        'articles': [_serialize_article(a) for a in pagination.items],
    })


@api_bp.route('/news/<int:article_id>')
def get_news(article_id):
    """Get a single article by ID."""
    article = Article.query.get_or_404(article_id)
    data = _serialize_article(article, full=True)
    data['companies'] = [
        {
            'id': ac.company_id,
            'name': ac.company.name,
            'slug': ac.company.slug,
            'sentiment': ac.sentiment,
            'sentiment_score': float(ac.sentiment_score) if ac.sentiment_score else None,
            'is_primary': ac.is_primary,
        }
        for ac in article.companies.all()
    ]
    data['categories'] = [
        {'name': c.name, 'slug': c.slug, 'name_zh': c.name_zh}
        for c in article.categories
    ]
    return jsonify(data)


@api_bp.route('/companies')
def list_companies():
    """List companies with pagination and filtering.

    Query params: page, per_page, q, sector, grenoble
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 30, type=int), 100)
    search = request.args.get('q', '').strip()
    sector = request.args.get('sector', '').strip()
    grenoble = request.args.get('grenoble')

    query = Company.query
    if search:
        query = query.filter(Company.name.like(f'%{search}%'))
    if sector:
        query = query.filter(Company.sector == sector)
    if grenoble == '1':
        query = query.filter(Company.is_grenoble == True)

    pagination = query.order_by(Company.name).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
        'companies': [_serialize_company(c) for c in pagination.items],
    })


@api_bp.route('/companies/<slug>')
def get_company(slug):
    """Get a single company by slug, including recent articles."""
    company = Company.query.filter_by(slug=slug).first_or_404()
    data = _serialize_company(company)
    data['recent_articles'] = [
        _serialize_article(a)
        for a in (
            Article.query
            .join(ArticleCompany)
            .filter(ArticleCompany.company_id == company.id)
            .order_by(Article.published_at.desc())
            .limit(10)
            .all()
        )
    ]
    return jsonify(data)


@api_bp.route('/sources')
def list_sources():
    """List all active news sources."""
    sources = NewsSource.query.filter_by(is_active=True).order_by(NewsSource.name).all()
    return jsonify({
        'sources': [
            {
                'id': s.id,
                'name': s.name,
                'slug': s.slug,
                'url': s.url,
                'feed_type': s.feed_type,
                'category': s.category,
                'last_crawled_at': s.last_crawled_at.isoformat() if s.last_crawled_at else None,
            }
            for s in sources
        ]
    })


def _serialize_article(article: Article, full: bool = False) -> dict:
    data = {
        'id': article.id,
        'url': article.url,
        'title_fr': article.title_fr,
        'title_zh': article.title_zh,
        'title_en': article.title_en,
        'summary_zh': article.summary_zh,
        'summary_en': article.summary_en,
        'source': article.source.name if article.source else None,
        'author': article.author,
        'image_url': article.image_url,
        'published_at': article.published_at.isoformat() if article.published_at else None,
        'llm_processed': article.llm_processed,
    }
    if full:
        data.update({
            'content_fr': article.content_fr,
            'content_zh': article.content_zh,
            'content_en': article.content_en,
            'summary_fr': article.summary_fr,
            'llm_provider': article.llm_provider,
            'llm_model': article.llm_model,
        })
    return data


def _serialize_company(company: Company) -> dict:
    return {
        'id': company.id,
        'name': company.name,
        'slug': company.slug,
        'aliases': company.aliases,
        'description': company.description,
        'website': company.website,
        'headquarters': company.headquarters,
        'sector': company.sector,
        'is_grenoble': company.is_grenoble,
        'article_count': company.article_count,
    }
