"""Collect paid results without business writes, then apply in one transaction."""
from datetime import date, datetime

from slugify import slugify
from sqlalchemy.orm import Session

from app.extensions import db
from app.llm.client import LLMClient
from app.models.article import Article, ArticleCategory, ArticleCompany
from app.models.category import Category
from app.models.company import Company
from app.utils.text import strip_html


def process_article(article_id, *, force=False, skip_translate=False):
    """Shared Celery/CLI pipeline. Returns whether a new result was committed.

    No business session/row lock spans a provider call. The final row lock and
    input check prevent concurrent consumers from applying stale results. This
    is not a lease: concurrent consumers can still pay for duplicate requests.
    """
    with Session(db.engine) as session:
        article = session.get(Article, article_id)
        if not article or (article.llm_processed and not force):
            return False
        title, content, version = article.title_fr, article.content_fr, article.updated_at
    client = LLMClient()
    has_content = bool((strip_html(content or '') or '').strip())
    text = content if has_content else title
    values = {}
    if not skip_translate:
        for lang in ('zh', 'en'):
            values[f'title_{lang}'] = client.translate(title, lang, article_id)
        for lang in ('zh', 'en'):
            values[f'content_{lang}'] = client.digest(title, content, lang, article_id) if has_content else None
    for lang in ('fr', 'zh', 'en'):
        values[f'summary_{lang}'] = client.summarize(text, lang, article_id)
    companies = []
    seen = set()
    for entry in client.extract_companies(text, article_id):
        name = entry['name'].strip()
        identity = slugify(name)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        companies.append((entry, client.analyze_sentiment(text, name, article_id)))
    classified = client.classify_category(text, article_id)
    values['highlights'] = classified['highlights'] or None
    values['event_date'] = date.fromisoformat(classified['event_date']) if classified.get('event_date') else None
    for lang in ('zh', 'en'):
        values[f'insight_{lang}'] = client.generate_insight(title, text, lang, article_id) if has_content else None
    route = client.routes.get('translate' if not skip_translate else 'summarize')
    if route:
        # Legacy single-route columns describe title translation (or summary
        # when skipped). The independent usage ledger is authoritative per task.
        values.update(llm_provider=route['provider'], llm_model=route['model'])
    values.update(llm_processed=True, llm_processed_at=datetime.utcnow())

    with Session(db.engine) as session, session.begin():
        article = session.query(Article).filter_by(id=article_id).with_for_update().one_or_none()
        if not article or (article.llm_processed and not force):
            return False
        if (article.title_fr, article.content_fr, article.updated_at) != (title, content, version):
            raise RuntimeError('Article changed during LLM processing; retry with fresh input')
        if force:
            session.query(ArticleCompany).filter_by(article_id=article_id, extracted_by='llm').delete()
            session.query(ArticleCategory).filter_by(article_id=article_id).delete()
        for key, value in values.items():
            setattr(article, key, value)
        _apply_companies(session, article_id, companies)
        _apply_categories(session, article_id, classified['categories'])
    return True


def _apply_companies(session, article_id, companies):
    linked = set()
    for entry, sentiment in companies:
        name = entry['name'].strip()
        slug = slugify(name)
        company = session.query(Company).filter_by(slug=slug).first()
        if not company:
            company = next((c for c in session.query(Company).all()
                            if name.casefold() in [a.casefold() for a in (c.aliases or [])]), None)
        if not company:
            company = Company(name=name, slug=slug, is_auto_created=True)
            session.add(company)
            session.flush()
        for field in ('spinoff_origin', 'company_stage'):
            if not getattr(company, field) and entry.get(field):
                setattr(company, field, entry[field])
        if company.id in linked:
            continue
        linked.add(company.id)
        link = session.query(ArticleCompany).filter_by(article_id=article_id, company_id=company.id).first()
        if link and link.extracted_by != 'llm':
            continue
        if not link:
            link = ArticleCompany(article_id=article_id, company_id=company.id, extracted_by='llm')
            session.add(link)
        link.sentiment = sentiment['sentiment']
        link.sentiment_score = sentiment['score']
        link.mention_count = entry['mentions']
        link.is_primary = entry['is_primary']


def _apply_categories(session, article_id, categories):
    for entry in categories:
        category = session.query(Category).filter_by(slug=entry['category']).first()
        if not category:
            continue
        link = session.get(ArticleCategory, (article_id, category.id))
        if not link:
            link = ArticleCategory(article_id=article_id, category_id=category.id)
            session.add(link)
        link.confidence = entry['confidence']
