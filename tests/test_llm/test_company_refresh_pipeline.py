"""Article completion queues coalesced company refresh intent; it never pays inline."""
from app.llm import prompts
from app.llm.tasks import process_article_llm
from app.models.article import Article
from app.models.company import Company
from tests.test_llm.test_pipeline import article_reply


def test_articles_queue_one_refresh_per_tracked_company_without_inline_model_calls(db, llm_env, monkeypatch):
    from celery import Celery
    sent = []
    monkeypatch.setattr(Celery, 'send_task', lambda self, name, args=None, kwargs=None, **options:
                        sent.append((name, args, options)))
    tracked = Company(name='Fixture Corp', slug='fixture-corp', ai_analysis={'overview': 'Tracked'})
    db.session.add(tracked)
    second = Article(source_id=llm_env.article.source_id, url='https://test.invalid/b',
                     title_fr='Second title', content_fr='Another synthetic Grenoble report.')
    db.session.add(second)
    db.session.commit()
    llm_env.provider.reply = article_reply

    process_article_llm.run(llm_env.article.id)
    process_article_llm.run(second.id)
    db.session.expire_all()

    assert not any(call['messages'][0]['content'] == prompts.COMPANY_ANALYSIS_SYSTEM
                   for call in llm_env.provider.calls), 'Article task must not pay for company analysis'
    refreshes = [item for item in sent if item[0] == 'app.llm.refresh_tasks.refresh']
    assert len(refreshes) == 1 and refreshes[0][2] == {'queue': 'llm'}
    assert db.session.query(Company).filter_by(slug='fixture-corp').one().ai_analysis == {'overview': 'Tracked'}


def test_untracked_company_mentions_queue_nothing(db, llm_env, monkeypatch):
    from celery import Celery
    sent = []
    monkeypatch.setattr(Celery, 'send_task', lambda self, name, args=None, kwargs=None, **options:
                        sent.append((name, args, options)))
    llm_env.provider.reply = article_reply
    process_article_llm.run(llm_env.article.id)
    assert not [item for item in sent if item[0] == 'app.llm.refresh_tasks.refresh']
