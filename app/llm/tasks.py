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
        # 1. Translate title and content
        article.title_zh = client.translate(article.title_fr, 'zh', article.id)
        article.title_en = client.translate(article.title_fr, 'en', article.id)

        if article.content_fr:
            article.content_zh = client.translate(article.content_fr, 'zh', article.id)
            article.content_en = client.translate(article.content_fr, 'en', article.id)

        # 2. Generate summaries
        article.summary_fr = client.summarize(text, 'fr', article.id)
        article.summary_zh = client.summarize(text, 'zh', article.id)
        article.summary_en = client.summarize(text, 'en', article.id)

        # 3. Extract companies (NER)
        companies = client.extract_companies(text, article.id)
        _link_companies(article, companies, client, text)

        # 4. Classify categories
        categories = client.classify_category(text, article.id)
        _link_categories(article, categories)

        # Mark as processed
        article.llm_processed = True
        article.llm_processed_at = datetime.utcnow()
        db.session.commit()

        logger.info(f'LLM processing complete for article {article_id}')

    except Exception as exc:
        logger.error(f'LLM processing failed for article {article_id}: {exc}')
        db.session.rollback()
        raise self.retry(exc=exc)


def _link_companies(article: Article, extracted: list[dict],
                    client: LLMClient, text: str):
    """Link extracted companies to the article, with sentiment analysis."""
    from slugify import slugify

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
                name=name, slug=slug, is_auto_created=True
            )
            db.session.add(company)
            db.session.flush()

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
