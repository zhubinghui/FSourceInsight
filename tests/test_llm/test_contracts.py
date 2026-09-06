from decimal import Decimal

import pytest

from app.llm.client import LLMClient
from app.models.llm import LLMUsageLog


@pytest.mark.parametrize('method,args,response', [
    ('extract_companies', ('text',), 'not json'),
    ('extract_companies', ('text',), []),
    ('extract_companies', ('text',), {'companies': [{'name': 'Fixture', 'mentions': True, 'is_primary': True}]}),
    ('extract_companies', ('text',), {'companies': [{'name': '', 'mentions': 1, 'is_primary': True}]}),
    ('extract_companies', ('text',), {'companies': [{'name': 'Fixture', 'mentions': 1, 'is_primary': 'yes'}]}),
    ('analyze_sentiment', ('text', 'Fixture'), {'sentiment': 'happy', 'score': 0.5, 'reason': 'reason'}),
    ('analyze_sentiment', ('text', 'Fixture'), {'sentiment': 'neutral', 'score': 4, 'reason': 'reason'}),
    ('analyze_sentiment', ('text', 'Fixture'), '{"sentiment":"neutral","score":NaN,"reason":"reason"}'),
    ('classify_category', ('text',), {'categories': 'research', 'highlights': [], 'event_date': None}),
    ('classify_category', ('text',), {'categories': [{'category': 'research', 'confidence': True}], 'highlights': [], 'event_date': None}),
    ('classify_category', ('text',), {'categories': [], 'highlights': ['unknown'], 'event_date': None}),
    ('classify_category', ('text',), {'categories': [], 'highlights': [], 'event_date': '2026-02-30'}),
    ('analyze_company', ('Fixture',), {}),
    ('analyze_company', ('Fixture',), []),
    ('translate', ('bonjour',), ''),
    ('translate', ('bonjour',), None),
])
def test_invalid_response_is_a_paid_failure_not_cached_success(db, llm_env, method, args, response):
    llm_env.provider.reply = response
    for _ in range(2):
        with pytest.raises(ValueError):
            getattr(LLMClient(), method)(*args)
    assert len(llm_env.provider.calls) == 2
    logs = LLMUsageLog.query.all()
    assert len(logs) == 2
    assert all(not log.success and log.cost_usd == Decimal('0.002000') for log in logs)


@pytest.mark.parametrize('method,args,response,expected', [
    ('extract_companies', ('text',), '```json\n{"companies": []}\n```', []),
    ('classify_category', ('text',), {'categories': [], 'highlights': [], 'event_date': None},
     {'categories': [], 'highlights': [], 'event_date': None}),
    ('analyze_sentiment', ('text', 'Fixture'), {'sentiment': 'neutral', 'score': 0, 'reason': 'No polarity'},
     {'sentiment': 'neutral', 'score': 0, 'reason': 'No polarity'}),
])
def test_valid_empty_or_neutral_results_remain_cacheable(llm_env, method, args, response, expected):
    llm_env.provider.reply = response
    client = LLMClient()
    assert getattr(client, method)(*args) == expected
    llm_env.provider.error = AssertionError('valid result should be cached')
    assert getattr(client, method)(*args) == expected


@pytest.mark.parametrize('reason', ['length', 'content_filter', 'tool_calls'])
def test_noncompleted_response_is_not_a_success(db, llm_env, reason):
    llm_env.provider.finish_reason = reason
    with pytest.raises(ValueError):
        LLMClient().translate('bonjour')
    log = LLMUsageLog.query.one()
    assert not log.success and log.cost_usd == Decimal('0.002000')
