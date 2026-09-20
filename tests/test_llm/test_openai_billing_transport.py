"""Public client → real LiteLLM/OpenAI SDK → synthetic HTTP, never a paid call."""
import json

from bs4 import BeautifulSoup
import httpx
import pytest

from app.llm.client import LLMClient
from app.models.llm import LLMConfig
from tests.test_llm.conftest import MemoryRedis


@pytest.mark.parametrize('model,input_price,output_price,reserved,settled', [
    ('gpt-5.4-mini', '0.000750', '0.004500', '0.318432', '0.000300'),
    ('gpt-5.4-nano', '0.000200', '0.001250', '0.085120', '0.000083'),
])
def test_reviewed_official_route_pays_at_explicit_standard_tier_with_reasoning_bound(
        db, client, login, monkeypatch, model, input_price, output_price, reserved, settled):
    cache = MemoryRedis()
    monkeypatch.setattr('app.llm.client.redis_client', cache)
    monkeypatch.setattr('app.llm.circuit_breaker.redis_client', cache)
    monkeypatch.setenv('SYNTHETIC_OPENAI_KEY', 'synthetic-not-a-real-key')
    db.session.add(LLMConfig(
        provider='openai', model=model, api_base_url='https://api.openai.com/v1',
        api_key_env_var='SYNTHETIC_OPENAI_KEY', tasks=['translate'], is_default=True,
        max_tokens=4096, temperature=0.3, billing_input_limit=400000, billing_output_limit=4096,
        cost_per_1k_input=input_price, cost_per_1k_output=output_price))
    db.session.commit()
    login('admin')
    sent = []

    def http_send(_client, request, **kwargs):
        assert str(request.url) == 'https://api.openai.com/v1/chat/completions'
        assert request.method == 'POST'
        body = json.loads(request.content)
        sent.append(body)
        # The public accounting page can see the committed permit BEFORE HTTP.
        page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
        row = page.select_one('[data-reservation-state=reserved]')
        assert row is not None and reserved in row.get_text()
        return httpx.Response(200, request=request, json={
            'id': 'chatcmpl-synthetic', 'object': 'chat.completion', 'created': 1,
            'model': model, 'service_tier': body.get('service_tier', 'auto'),
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': '中文译文'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
                      'completion_tokens_details': {'reasoning_tokens': 40}},
        })

    monkeypatch.setattr(httpx.Client, 'send', http_send)
    assert LLMClient().translate('Synthetic French input') == '中文译文'
    assert len(sent) == 1
    assert sent[0].get('service_tier') == 'default'
    assert sent[0]['max_completion_tokens'] == 4096
    assert 'max_tokens' not in sent[0]
    assert sent[0]['model'] == model
    assert 'tools' not in sent[0] and 'modalities' not in sent[0]
    page = BeautifulSoup(client.get('/admin/llm-usage').text, 'html.parser')
    row = page.select_one('[data-reservation-state=settled]')
    assert row is not None and settled in row.get_text()  # all 50 output tokens, including reasoning
    assert LLMClient().translate('Synthetic French input') == '中文译文'
    assert len(sent) == 1  # validated response cache does not create another payment


def test_standard_tier_does_not_reuse_a_persisted_legacy_auto_tier_response(db, llm_env):
    config = llm_env.config
    assert config.id == 1
    config.provider, config.model = 'openai', 'gpt-5.4-mini'
    config.api_base_url = 'https://api.openai.com/v1'
    db.session.commit()
    # Synthetic Redis wire fixture captured before the standard-tier cache change:
    # prompt 2026-09-06.2 / contract 1 / config 1, same endpoint and effective input.
    # Do not recompute this historical key with the client under test.
    llm_env.cache.setex(
        'llm_cache:v2:d5c6bd134d06c97d5dce45e8003315f824cb5707468085b4287f18a29b85132f',
        604800, b'Legacy auto-tier response')
    assert LLMClient().translate('Previously cached input') == 'Translated text'
    assert len(llm_env.provider.calls) == 1
    assert llm_env.provider.calls[0]['service_tier'] == 'default'


def test_admin_explains_the_explicit_official_endpoint_processing_contract(client, login):
    login('admin')
    response = client.get('/admin/llm-config/new')
    assert response.status_code == 200
    assert 'service_tier=default' in response.text
    assert 'https://api.openai.com/v1' in response.text


@pytest.mark.parametrize('provider,model,endpoint', [
    ('openai', 'gpt-5.4-mini', None),
    ('openai', 'gpt-5.4-mini', 'https://gateway.invalid/v1'),
    ('deepseek', 'deepseek-v4-flash', 'https://api.deepseek.com/v1'),
    ('openai', 'anthropic/claude-sonnet-4-20250514', 'https://api.openai.com/v1'),
])
def test_other_routes_do_not_receive_an_unreviewed_openai_specific_option(
        db, llm_env, provider, model, endpoint):
    config = llm_env.config
    config.provider, config.model, config.api_base_url = provider, model, endpoint
    db.session.commit()
    assert LLMClient().translate('Keep the existing transport contract') == 'Translated text'
    assert 'service_tier' not in llm_env.provider.calls[0]
