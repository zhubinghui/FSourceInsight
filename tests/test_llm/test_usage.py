from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models.article import Article
from app.models.llm import LLMConfig, LLMUsageLog


@pytest.mark.parametrize('failed', [False, True])
def test_usage_survives_caller_rollback_without_committing_article(db, llm_env, failed):
    article_id = llm_env.article.id
    llm_env.article.title_zh = 'Uncommitted business change'
    if failed:
        llm_env.provider.error = RuntimeError('synthetic provider failure')
        with pytest.raises(RuntimeError, match='synthetic provider failure'):
            LLMClient().translate('bonjour', article_id=article_id)
    else:
        assert LLMClient().translate('bonjour', article_id=article_id) == 'Translated text'
    db.session.rollback()
    with Session(db.engine) as observer:
        assert observer.get(Article, article_id).title_zh is None
        usage = observer.query(LLMUsageLog).one()
        assert usage.article_id == article_id
        assert usage.success is (not failed)
        if not failed:
            assert usage.cost_usd == Decimal('0.002000')
            assert (usage.input_tokens, usage.output_tokens) == (100, 50)


def test_fallback_attempts_each_config_at_most_once(db, llm_env):
    db.session.add(LLMConfig(provider='second', model='backup', tasks=['translate']))
    db.session.commit()
    llm_env.provider.error = RuntimeError('all providers failed')
    with pytest.raises(RuntimeError, match='all providers failed'):
        LLMClient().translate('bonjour')
    assert [c['model'] for c in llm_env.provider.calls] == ['synthetic/primary', 'second/backup']
    assert LLMUsageLog.query.count() == 2


def test_budget_is_rechecked_before_paid_fallback(app, db, llm_env):
    db.session.add(LLMConfig(provider='second', model='backup', tasks=['ner']))
    db.session.commit()
    app.config['LLM_DAILY_BUDGET_USD'] = 0.001
    llm_env.provider.reply = 'invalid JSON but billable tokens'
    with pytest.raises(RuntimeError, match='budget exceeded'):
        LLMClient().extract_companies('text')
    assert len(llm_env.provider.calls) == 1
    assert LLMUsageLog.query.one().cost_usd == Decimal('0.002000')


def test_ledger_failure_does_not_repeat_provider_call(db, llm_env):
    db.session.add(LLMConfig(provider='second', model='backup', tasks=['translate']))
    db.session.commit()

    def fail_ledger(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO llm_usage_log '):
            raise RuntimeError('synthetic ledger outage')
    event.listen(db.engine, 'before_cursor_execute', fail_ledger)
    try:
        with pytest.raises(RuntimeError, match='synthetic ledger outage'):
            LLMClient().translate('bonjour')
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_ledger)
    assert len(llm_env.provider.calls) == 1
    assert not any(key.startswith('llm_cache:') for key in llm_env.cache.values)


def test_sdk_cannot_add_hidden_retries_to_attempt_limit(llm_env):
    LLMClient().translate('bonjour')
    assert llm_env.provider.calls[0]['num_retries'] == 0
    assert llm_env.provider.calls[0]['timeout'] == 60
