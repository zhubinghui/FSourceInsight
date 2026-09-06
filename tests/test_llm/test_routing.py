from bs4 import BeautifulSoup
import pytest

from app.llm.client import LLMClient
from app.models.llm import LLMConfig


def test_explicit_primary_beats_cheaper_fallback_and_priority_orders_primaries(db, llm_env):
    llm_env.config.role = 'fallback'
    llm_env.config.priority = 0
    primary = LLMConfig(provider='second', model='chosen', tasks=['translate'], cost_per_1k_input='0.1')
    primary.role = 'primary'
    primary.priority = 10
    expensive = LLMConfig(provider='third', model='later', tasks=['translate'], cost_per_1k_input='0.05')
    expensive.role = 'primary'
    expensive.priority = 20
    db.session.add_all([primary, expensive])
    db.session.commit()
    LLMClient().translate('bonjour')
    assert llm_env.provider.calls[0]['model'] == 'second/chosen'


def test_open_default_is_not_used_as_last_resort(llm_env):
    llm_env.cache.setex('cb:synthetic:failures', 3600, '5')
    import time
    llm_env.cache.setex('cb:synthetic:opened_at', 3600, str(time.time()))
    with pytest.raises(RuntimeError, match='No available LLM config'):
        LLMClient().translate('bonjour')
    assert not llm_env.provider.calls


def test_admin_can_persist_priority_and_role(client, login, csrf_token, db, llm_env):
    login('admin')
    path = f'/admin/llm-config/{llm_env.config.id}/edit'
    response = client.post(path, data={
        'csrf_token': csrf_token(path), 'provider': 'synthetic', 'model': 'primary',
        'role': 'fallback', 'priority': '7', 'tasks': ['translate'],
    })
    assert response.status_code == 302
    db.session.expire_all()
    saved = db.session.get(LLMConfig, llm_env.config.id)
    assert saved.role == 'fallback' and saved.priority == 7
    page = BeautifulSoup(client.get(path).text, 'html.parser')
    assert page.select_one('input[name=priority]')['value'] == '7'
    assert page.select_one('select[name=role] option[selected]')['value'] == 'fallback'


@pytest.mark.parametrize('role,priority', [('bogus', '1'), ('primary', '-1'), ('primary', 'abc'), ('primary', '10001')])
def test_admin_rejects_invalid_route_without_partial_save(client, login, csrf_token, db, llm_env, role, priority):
    login('admin')
    path = f'/admin/llm-config/{llm_env.config.id}/edit'
    response = client.post(path, data={'csrf_token': csrf_token(path), 'provider': 'changed',
                                      'model': 'changed', 'role': role, 'priority': priority})
    assert response.status_code == 400
    db.session.expire_all()
    assert db.session.get(LLMConfig, llm_env.config.id).model == 'primary'


def test_fresh_seed_uses_documented_primary_and_never_overwrites_existing(db, llm_env):
    from scripts.seed_llm_configs import seed
    LLMConfig.query.delete()
    db.session.commit()
    seed()
    llm_env.provider.reply = {'companies': []}
    LLMClient().extract_companies('article')
    assert llm_env.provider.calls[-1]['model'] == 'openai/gpt-5.4-mini'
    llm_env.provider.reply = 'Insight'
    LLMClient().generate_insight('title', 'body')
    assert llm_env.provider.calls[-1]['model'] == 'openai/gpt-5.4-mini'
    LLMClient().digest('title', 'body')
    assert llm_env.provider.calls[-1]['model'] == 'deepseek/deepseek-chat'
    mini = LLMConfig.query.filter_by(model='gpt-5.4-mini').one()
    mini.role, mini.priority, mini.tasks = 'fallback', 321, ['ner']
    db.session.commit()
    seed()
    saved = LLMConfig.query.filter_by(model='gpt-5.4-mini').one()
    assert (saved.role, saved.priority, saved.tasks) == ('fallback', 321, ['ner'])
