import logging
from datetime import datetime

from celery_app import celery
from app.extensions import db
from app.models.article import Article, ArticleCompany
from app.models.company import Company
from app.llm.client import LLMClient
from app.llm.pipeline import process_article

logger = logging.getLogger(__name__)


@celery.task(name='app.llm.tasks.process_article_llm', bind=True,
             max_retries=2, default_retry_delay=120, queue='llm',
             rate_limit='10/m')
def process_article_llm(self, article_id: int, force=False, skip_translate=False):
    """Full pipeline; the shared implementation also serves the manual CLI."""
    try:
        applied = process_article(article_id, force=force, skip_translate=skip_translate)
    except Exception as exc:
        logger.error(f'LLM processing failed for article {article_id}: {exc}')
        db.session.rollback()
        raise self.retry(exc=exc)
    if applied:
        # Best-effort follow-up cannot roll back a committed article. It is not
        # a durable outbox; delivery/recovery is deferred to M2.
        db.session.expire_all()
        article = db.session.get(Article, article_id)
        if article:
            _refresh_company_analyses(article, LLMClient())
        logger.info(f'LLM processing complete for article {article_id}')


def _refresh_company_analyses(article: Article, client: LLMClient):
    """Auto-refresh AI analysis for companies linked to this article.

    Only refreshes companies that already have an ai_analysis (i.e., were
    previously analyzed). This avoids generating analyses for every company
    mentioned in every article — only tracked companies get updated.
    """
    linked = (
        ArticleCompany.query
        .filter_by(article_id=article.id)
        .all()
    )
    for ac in linked:
        company = ac.company
        if not company or not company.ai_analysis:
            continue

        try:
            # Gather latest 5 news headlines for context
            recent = (
                Article.query
                .join(ArticleCompany)
                .filter(ArticleCompany.company_id == company.id)
                .order_by(Article.published_at.desc())
                .limit(5)
                .all()
            )
            news = '\n'.join([
                f'- {a.title_fr or a.title_en or ""}'
                for a in recent
            ])

            analysis = client.analyze_company(
                name=company.name,
                sector=company.sector,
                headquarters=company.headquarters,
                description=company.description,
                spinoff_origin=company.spinoff_origin,
                company_stage=company.company_stage,
                recent_news=news,
            )
            trigger = f'Article #{article.id}: {(article.title_fr or "")[:60]}'
            _save_revision(company, new_data=analysis, source='auto-refresh', trigger=trigger)
            company.ai_analysis = analysis
            company.ai_analysis_at = datetime.utcnow()
            db.session.commit()
            logger.info(f'Auto-refreshed AI analysis for {company.name}')
        except Exception as e:
            db.session.rollback()
            logger.warning(f'Failed to refresh analysis for {company.name}: {e}')


ANALYSIS_FIELDS = [
    ('website', '公司主页'),
    ('overview', '公司概况'),
    ('founders', '创始人'),
    ('spinoff_source', 'Spin-off来源'),
    ('core_tech', '核心技术'),
    ('cn_competitor_names', '中国对标企业'),
    ('business_status', '经营现状'),
    ('recommendation', '关注建议'),
    ('recommendation_reason', '建议理由'),
]


def _save_revision(company, new_data=None, source='manual', trigger=''):
    """Track field-level changes in revision history.

    Compares old ai_analysis (dict) with new_data and records which fields changed.
    """
    old_data = company.ai_analysis or {}
    if not isinstance(old_data, dict):
        old_data = {}
    if new_data is None:
        return

    changes = []
    for field_key, field_label in ANALYSIS_FIELDS:
        old_val = str(old_data.get(field_key, '') or '')
        new_val = str(new_data.get(field_key, '') or '')
        if old_val != new_val and (old_val or new_val):
            changes.append({
                'field': field_label,
                'field_key': field_key,
                'old': old_val[:200] if old_val else '',
                'new': new_val[:200] if new_val else '',
            })

    # Also check competitors table
    old_comp = old_data.get('competitors', [])
    new_comp = new_data.get('competitors', [])
    if str(old_comp) != str(new_comp):
        changes.append({
            'field': '对标对比表',
            'field_key': 'competitors',
            'old': '(table updated)',
            'new': '(table updated)',
        })

    if not changes:
        return

    history = company.ai_revision_history or []
    history.append({
        'timestamp': datetime.utcnow().isoformat(),
        'source': source,
        'trigger': trigger,
        'changes': changes,
    })
    company.ai_revision_history = history[-10:]


@celery.task(name='app.llm.tasks.refresh_company_analysis', bind=True,
             max_retries=2, default_retry_delay=60, queue='llm')
def refresh_company_analysis(self, company_id: int):
    """Async AI Refresh triggered by the company detail page.

    Crawls the company homepage, runs LLM analyze_company with the website
    excerpt, merges only non-empty fields onto the previous ai_analysis,
    and records a revision tagged 'ai-refresh-website' or 'ai-refresh-news'.
    """
    from app.utils.website_fetcher import fetch_website_excerpt

    company = db.session.get(Company, company_id)
    if not company:
        logger.error(f'refresh_company_analysis: company {company_id} not found')
        return

    site_url = None
    if isinstance(company.ai_analysis, dict):
        site_url = (company.ai_analysis.get('website') or '').strip() or None
    if not site_url:
        site_url = company.website

    website_excerpt, fetch_status = (None, 'no_url')
    if site_url:
        website_excerpt, fetch_status = fetch_website_excerpt(site_url)
    logger.info(
        f'refresh_company_analysis: company={company.name} site={site_url} '
        f'fetch_status={fetch_status} excerpt_len={len(website_excerpt or "")}'
    )

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
    except Exception as exc:
        logger.error(
            f'refresh_company_analysis: LLM call failed for {company.name}: {exc}',
            exc_info=True,
        )
        raise self.retry(exc=exc)

    old = company.ai_analysis if isinstance(company.ai_analysis, dict) else {}
    merged = dict(old)
    for key, val in analysis.items():
        if key == 'competitors':
            if isinstance(val, list) and val:
                merged['competitors'] = val
            continue
        if val not in (None, '', []):
            merged[key] = val

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
    logger.info(
        f'refresh_company_analysis: company={company.name} done source={revision_source}'
    )
