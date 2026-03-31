import logging
from datetime import datetime

from celery_app import celery
from app.extensions import db
from app.models.article import Article, ArticleCompany, ArticleCategory
from app.models.company import Company
from app.models.category import Category
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)


@celery.task(name='app.llm.tasks.process_article_llm', bind=True,
             max_retries=2, default_retry_delay=120, queue='llm',
             rate_limit='10/m')
def process_article_llm(self, article_id: int):
    """Full LLM processing pipeline for a single article."""
    article = db.session.get(Article, article_id)
    if not article:
        logger.error(f'Article {article_id} not found')
        return

    if article.llm_processed:
        logger.info(f'Article {article_id} already processed, skipping')
        return

    client = LLMClient()
    text = article.content_fr or article.title_fr

    try:
        # 1. Translate title
        article.title_zh = client.translate(article.title_fr, 'zh', article.id)
        article.title_en = client.translate(article.title_fr, 'en', article.id)

        # 2. Digest content (detailed rewrite, not literal translation)
        if article.content_fr:
            article.content_zh = client.digest(
                article.title_fr, article.content_fr, 'zh', article.id
            )
            article.content_en = client.digest(
                article.title_fr, article.content_fr, 'en', article.id
            )

        # 3. Generate summaries
        article.summary_fr = client.summarize(text, 'fr', article.id)
        article.summary_zh = client.summarize(text, 'zh', article.id)
        article.summary_en = client.summarize(text, 'en', article.id)

        # 3. Extract companies (NER)
        companies = client.extract_companies(text, article.id)
        _link_companies(article, companies, client, text)

        # 4. Classify categories + detect highlights
        classify_result = client.classify_category(text, article.id)
        _link_categories(article, classify_result['categories'])
        article.highlights = classify_result['highlights'] or None
        if classify_result.get('event_date'):
            try:
                from datetime import date
                article.event_date = date.fromisoformat(classify_result['event_date'])
            except (ValueError, TypeError):
                pass

        # 5. Generate strategic insight analysis
        article.insight_zh = client.generate_insight(
            article.title_fr, text, 'zh', article.id
        )
        article.insight_en = client.generate_insight(
            article.title_fr, text, 'en', article.id
        )

        # Mark as processed with provider/model info
        config = client._get_config('translate') or client._get_config('summarize')
        article.llm_processed = True
        article.llm_processed_at = datetime.utcnow()
        if config:
            article.llm_provider = config.provider
            article.llm_model = config.model
        db.session.commit()

        # 6. Auto-refresh AI analysis for linked companies that already have one
        _refresh_company_analyses(article, client)

        logger.info(f'LLM processing complete for article {article_id}')

    except Exception as exc:
        logger.error(f'LLM processing failed for article {article_id}: {exc}')
        db.session.rollback()
        raise self.retry(exc=exc)


def _link_companies(article: Article, extracted: list[dict],
                    client: LLMClient, text: str):
    """Link extracted companies to the article, with sentiment analysis."""
    from slugify import slugify

    linked_company_ids = set()

    for entry in extracted:
        name = entry.get('name', '').strip()
        if not name or len(name) < 2:
            continue

        slug = slugify(name)

        # Try to find existing company by name or alias
        company = Company.query.filter_by(slug=slug).first()
        if not company:
            # Check aliases
            all_companies = Company.query.all()
            for c in all_companies:
                if c.aliases and name.lower() in [a.lower() for a in c.aliases]:
                    company = c
                    break

        if not company:
            company = Company(
                name=name, slug=slug, is_auto_created=True,
                spinoff_origin=entry.get('spinoff_origin'),
                company_stage=entry.get('company_stage'),
            )
            db.session.add(company)
            db.session.flush()
        else:
            # Enrich existing company with spin-off info if newly discovered
            if not company.spinoff_origin and entry.get('spinoff_origin'):
                company.spinoff_origin = entry['spinoff_origin']
            if not company.company_stage and entry.get('company_stage'):
                company.company_stage = entry['company_stage']

        # Skip if this company was already linked to this article
        if company.id in linked_company_ids:
            continue
        existing = ArticleCompany.query.filter_by(
            article_id=article.id, company_id=company.id
        ).first()
        if existing:
            continue
        linked_company_ids.add(company.id)

        # Sentiment analysis for this company
        sentiment_data = client.analyze_sentiment(text, name, article.id)

        ac = ArticleCompany(
            article_id=article.id,
            company_id=company.id,
            sentiment=sentiment_data.get('sentiment', 'neutral'),
            sentiment_score=sentiment_data.get('score', 0.0),
            mention_count=entry.get('mentions', 1),
            is_primary=entry.get('is_primary', False),
            extracted_by='llm',
        )
        db.session.add(ac)


def _link_categories(article: Article, classified: list[dict]):
    """Link classified categories to the article."""
    for entry in classified:
        slug = entry.get('category', '').strip()
        confidence = entry.get('confidence', 0.5)

        category = Category.query.filter_by(slug=slug).first()
        if not category:
            continue

        ac = ArticleCategory(
            article_id=article.id,
            category_id=category.id,
            confidence=confidence,
        )
        db.session.add(ac)


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
            logger.warning(f'Failed to refresh analysis for {company.name}: {e}')


ANALYSIS_FIELDS = [
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
