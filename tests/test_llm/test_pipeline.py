import pytest
from sqlalchemy import event

from app.llm.tasks import process_article_llm
from app.models.article import Article, ArticleCategory, ArticleCompany
from app.models.category import Category
from app.models.company import Company
from app.models.llm import LLMUsageLog


def article_reply(call):
    system = call['messages'][0]['content']
    if 'Named Entity Recognition' in system:
        return {'companies': [{'name': 'Fixture Corp', 'mentions': 2, 'is_primary': True},
                              {'name': 'Fixture Corp', 'mentions': 2, 'is_primary': True}]}
    if 'sentiment analysis specialist' in system:
        return {'sentiment': 'positive', 'score': 0.8, 'reason': 'New research'}
    if 'tech news classifier' in system:
        return {'categories': [{'category': 'research', 'confidence': 0.9},
                               {'category': 'research', 'confidence': 0.9}],
                'highlights': ['local_research'], 'event_date': None}
    return 'Synthetic enriched text'


def test_late_llm_failure_keeps_business_unchanged_and_retry_is_idempotent(db, llm_env):
    article_id = llm_env.article.id
    db.session.add(Category(name='Research', slug='research'))
    db.session.commit()
    llm_env.provider.reply = article_reply

    def fail_insight(call):
        if 'concise tech industry analyst' in call['messages'][0]['content']:
            raise RuntimeError('synthetic insight failure')
    llm_env.provider.before = fail_insight
    with pytest.raises(Exception, match='synthetic insight failure'):
        process_article_llm.run(article_id)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert article.title_zh is None
    assert not article.llm_processed
    assert Company.query.count() == ArticleCompany.query.count() == ArticleCategory.query.count() == 0
    assert LLMUsageLog.query.filter_by(success=True).count() > 0

    llm_env.provider.before = None
    process_article_llm.run(article_id)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert article.llm_processed
    assert article.insight_en == 'Synthetic enriched text'
    assert ArticleCategory.query.count() == ArticleCompany.query.count() == Company.query.count() == 1
    assert ArticleCompany.query.one().sentiment_score == 0.8
    process_article_llm.run(article_id)
    assert ArticleCategory.query.count() == ArticleCompany.query.count() == 1


@pytest.mark.parametrize('step', range(1, 13))
def test_each_provider_step_failure_leaves_no_partial_article(db, llm_env, step):
    article_id = llm_env.article.id
    llm_env.provider.reply = article_reply

    def interrupt(call):
        if len(llm_env.provider.calls) == step:
            raise RuntimeError('synthetic step interruption')
    llm_env.provider.before = interrupt
    with pytest.raises(Exception, match='synthetic step interruption'):
        process_article_llm.run(article_id)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert not article.llm_processed
    assert article.title_zh is article.summary_fr is article.insight_en is None
    assert Company.query.count() == ArticleCompany.query.count() == ArticleCategory.query.count() == 0
    llm_env.provider.before = None
    process_article_llm.run(article_id)
    db.session.expire_all()
    assert db.session.get(Article, article_id).llm_processed
    assert ArticleCompany.query.count() == 1


def test_late_business_failure_rolls_back_but_keeps_paid_usage(db, llm_env):
    article_id = llm_env.article.id
    db.session.add(Category(name='Research', slug='research'))
    db.session.commit()
    llm_env.provider.reply = article_reply

    def fail_category(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO article_category '):
            raise RuntimeError('synthetic database failure')
    event.listen(db.engine, 'before_cursor_execute', fail_category)
    try:
        with pytest.raises(Exception, match='synthetic database failure'):
            process_article_llm.run(article_id)
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_category)
    db.session.expire_all()
    assert not db.session.get(Article, article_id).llm_processed
    assert Company.query.count() == ArticleCompany.query.count() == 0
    assert LLMUsageLog.query.filter_by(success=True).count() == 12
    process_article_llm.run(article_id)
    db.session.expire_all()
    assert db.session.get(Article, article_id).llm_processed
    assert ArticleCompany.query.count() == ArticleCategory.query.count() == 1


def test_cli_force_failure_preserves_previous_result(db, llm_env, monkeypatch, capsys):
    from scripts.run_llm_process import main
    article = llm_env.article
    article_id = article.id
    article.llm_processed = True
    article.title_zh = 'Previous title'
    company = Company(name='Existing', slug='existing')
    db.session.add(company)
    db.session.flush()
    db.session.add(ArticleCompany(article_id=article_id, company_id=company.id))
    db.session.commit()
    llm_env.provider.error = RuntimeError('synthetic failure')
    monkeypatch.setattr('sys.argv', ['run_llm_process.py', '-a', str(article_id), '--force'])
    # The real CLI factory uses the isolated TestingConfig database.
    main()
    db.session.expire_all()
    assert db.session.get(Article, article_id).title_zh == 'Previous title'
    assert ArticleCompany.query.count() == 1
    assert '1 failed' in capsys.readouterr().out


def test_article_records_actual_fallback_not_configured_primary(db, llm_env):
    from app.models.llm import LLMConfig
    article_id = llm_env.article.id
    db.session.add(LLMConfig(provider='second', model='backup', tasks=['translate']))
    db.session.commit()
    llm_env.provider.reply = article_reply
    def fail_translation(call):
        if 'professional translator' in call['messages'][0]['content'] and call['model'] == 'synthetic/primary':
            raise RuntimeError('primary unavailable')
    llm_env.provider.before = fail_translation
    process_article_llm.run(article_id)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert (article.llm_provider, article.llm_model) == ('second', 'backup')


@pytest.mark.parametrize('content', [None, '  ', '<p> </p>'])
def test_title_only_article_has_no_deep_insight(db, llm_env, content):
    article_id = llm_env.article.id
    llm_env.article.content_fr = content
    db.session.commit()
    llm_env.provider.reply = article_reply
    process_article_llm.run(article_id)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert article.llm_processed
    assert article.insight_zh is article.insight_en is None
    assert LLMUsageLog.query.filter_by(task_type='insight').count() == 0


def test_retry_reuses_legacy_partial_relations_and_preserves_manual_sentiment(db, llm_env):
    article_id = llm_env.article.id
    company = Company(name='Fixture Corp', slug='fixture-corp')
    category = Category(name='Research', slug='research')
    db.session.add_all([company, category])
    db.session.flush()
    db.session.add_all([ArticleCategory(article_id=article_id, category_id=category.id, confidence=0.4),
                       ArticleCompany(article_id=article_id, company_id=company.id, extracted_by='manual',
                                      sentiment='negative', sentiment_score=-0.8)])
    db.session.commit()
    llm_env.provider.reply = article_reply
    process_article_llm.run(article_id)
    db.session.expire_all()
    assert ArticleCategory.query.count() == ArticleCompany.query.count() == 1
    assert ArticleCategory.query.one().confidence == 0.9
    assert ArticleCompany.query.one().sentiment_score == -0.8


def test_changed_input_is_not_overwritten_by_old_llm_result(db, llm_env):
    from sqlalchemy.orm import Session
    article_id = llm_env.article.id
    llm_env.provider.reply = article_reply
    def change_source(call):
        if len(llm_env.provider.calls) == 1:
            with Session(db.engine) as session, session.begin():
                session.get(Article, article_id).title_fr = 'New source title'
    llm_env.provider.before = change_source
    with pytest.raises(Exception, match='Article changed'):
        process_article_llm.run(article_id)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert article.title_fr == 'New source title' and article.title_zh is None
    assert not article.llm_processed
    assert Company.query.count() == ArticleCompany.query.count() == 0


def test_force_reprocess_without_body_clears_stale_digests(db, llm_env):
    article_id = llm_env.article.id
    llm_env.article.llm_processed = True
    llm_env.article.content_fr = None
    llm_env.article.content_zh = llm_env.article.content_en = 'Obsolete body'
    db.session.commit()
    llm_env.provider.reply = article_reply
    process_article_llm.run(article_id, force=True)
    db.session.expire_all()
    article = db.session.get(Article, article_id)
    assert article.content_zh is article.content_en is None
