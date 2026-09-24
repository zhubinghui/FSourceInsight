import logging
from datetime import datetime

from celery_app import celery
from app.extensions import db
from app.models.article import ArticleCompany
from app.models.company import Company
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
        # Only durable, coalesced intent; the model is never called here.
        _queue_company_refreshes(article_id)
        logger.info(f'LLM processing complete for article {article_id}')


def _queue_company_refreshes(article_id: int):
    """Queue one refresh per linked company that already has an analysis.

    An active job for the company absorbs this request, so a burst of articles
    about one company costs at most one refresh at a time.
    """
    from app.llm import company_refresh
    db.session.expire_all()
    linked = (
        db.session.query(Company.id)
        .join(ArticleCompany, ArticleCompany.company_id == Company.id)
        .filter(ArticleCompany.article_id == article_id, Company.ai_analysis.isnot(None))
        .all()
    )
    for (company_id,) in linked:
        try:
            identity, created = company_refresh.request(company_id, 'article', f'article:{article_id}')
            if created:
                company_refresh.publish(identity)
        except Exception:
            logger.warning(f'Company refresh intent unavailable for company {company_id}')


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

    # Copy: appending to the loaded JSON list in place leaves the committed
    # value equal to the new one, so no UPDATE would be emitted.
    history = list(company.ai_revision_history or [])
    history.append({
        'timestamp': datetime.utcnow().isoformat(),
        'source': source,
        'trigger': trigger,
        'changes': changes,
    })
    company.ai_revision_history = history[-10:]


@celery.task(name='app.llm.tasks.refresh_company_analysis', bind=True, queue='llm')
def refresh_company_analysis(self, company_id: int):
    """Retired message format: carries no durable job, so it never pays.

    Kept registered only so messages queued by the previous release are
    drained. Request a new AI Refresh from the company page instead.
    """
    logger.warning(f'Ignored legacy refresh message for company {company_id}; no durable job')
