import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.llm.client import LLMClient
from app.llm import prompts
from app.models.llm import LLMConfig, LLMUsageLog

COMPANY_RESPONSE = {
    'overview': '公司概况', 'founders': '', 'spinoff_source': '', 'core_tech': '芯片',
    'competitors': [], 'cn_competitor_names': '', 'business_status': '',
    'recommendation': '持续监控', 'recommendation_reason': '', 'website': '',
}


@pytest.mark.parametrize('field', ['name', 'sector', 'headquarters', 'description', 'spinoff_origin',
                                  'company_stage', 'recent_news', 'website_excerpt'])
def test_company_cache_tracks_every_effective_input(llm_env, field):
    llm_env.provider.reply = COMPANY_RESPONSE
    args = dict(name='Fixture', sector='chips', headquarters='Grenoble', description='old description',
                spinoff_origin='CEA', company_stage='startup', recent_news='old news', website_excerpt='old site')
    client = LLMClient()
    assert client.analyze_company(**args)['overview'] == '公司概况'
    args[field] = 'changed input'
    llm_env.provider.reply = dict(COMPANY_RESPONSE, overview='新概况')
    assert client.analyze_company(**args)['overview'] == '新概况'


@pytest.mark.parametrize('method', ['digest', 'generate_insight'])
def test_title_changes_invalidate_article_cache(llm_env, method):
    client = LLMClient()
    assert getattr(client, method)('old title', 'unchanged body') == 'Translated text'
    llm_env.provider.reply = 'New result'
    assert getattr(client, method)('new title', 'unchanged body') == 'New result'


@pytest.mark.parametrize('change', ['prompt', 'version', 'model', 'temperature', 'max_tokens', 'endpoint'])
def test_cache_tracks_prompt_versions_and_provider_settings(db, llm_env, monkeypatch, change):
    client = LLMClient()
    assert client.translate('bonjour') == 'Translated text'
    if change == 'prompt':
        monkeypatch.setattr(prompts, 'TRANSLATE_SYSTEM', prompts.TRANSLATE_SYSTEM + ' Be brief.')
    elif change == 'version':
        monkeypatch.setattr(prompts, 'PROMPT_VERSION', 'test-v2', raising=False)
    else:
        field = {'model': 'model', 'temperature': 'temperature', 'max_tokens': 'max_tokens', 'endpoint': 'api_base_url'}[change]
        value = {'model': 'updated', 'temperature': 0, 'max_tokens': 123, 'endpoint': 'https://test.invalid/v2'}[change]
        setattr(llm_env.config, field, value)
        db.session.commit()
    llm_env.provider.reply = 'New result'
    assert client.translate('bonjour') == 'New result'
    if change == 'temperature':
        assert llm_env.provider.calls[-1]['temperature'] == 0


def test_corrupt_cache_is_treated_as_miss(llm_env):
    llm_env.provider.reply = {'companies': []}
    client = LLMClient()
    assert client.extract_companies('text') == []
    for key in list(llm_env.cache.values):
        if key.startswith('llm_cache:'):
            llm_env.cache.values[key] = b'{"companies": "wrong shape"}'
    assert client.extract_companies('text') == []
    assert len(llm_env.provider.calls) == 2


def test_response_cache_outage_does_not_lose_paid_result(llm_env, monkeypatch):
    def unavailable(*args):
        raise RedisConnectionError('synthetic cache unavailable')
    # Only the optional response-cache transport is down; breaker is unchanged.
    from types import SimpleNamespace
    monkeypatch.setattr('app.llm.client.redis_client', SimpleNamespace(get=unavailable, setex=unavailable))
    assert LLMClient().translate('bonjour') == 'Translated text'
    assert len(llm_env.provider.calls) == 1


def test_recovered_primary_never_receives_fallback_cached_result(db, llm_env):
    db.session.add(LLMConfig(provider='second', model='backup', tasks=['translate']))
    db.session.commit()
    def fail_primary(call):
        if call['model'] == 'synthetic/primary':
            raise RuntimeError('primary down')
    llm_env.provider.before = fail_primary
    llm_env.provider.reply = 'Backup output'
    assert LLMClient().translate('bonjour') == 'Backup output'
    llm_env.provider.before = None
    llm_env.provider.reply = 'Primary output'
    assert LLMClient().translate('bonjour') == 'Primary output'
    assert LLMUsageLog.query.filter_by(success=True).count() == 2
