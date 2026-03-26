from datetime import datetime

from flask import Blueprint, render_template, request
from app.extensions import db
from app.models.article import Article, ArticleCompany
from app.models.source import NewsSource
from app.models.category import Category
from app.models.company import Company

news_bp = Blueprint('news', __name__)


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

    return query


def _get_filter_options():
    """Get dropdown options for filters."""
    return {
        'sources': NewsSource.query.filter_by(is_active=True).order_by(NewsSource.name).all(),
        'categories': Category.query.order_by(Category.name).all(),
        'companies': Company.query.order_by(Company.name).all(),
    }


@news_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = _build_article_query()
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    options = _get_filter_options()

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
    )


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
