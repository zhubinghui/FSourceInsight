"""Mock only provider/cache transports; exercise real client, ORM and tasks."""
import json
from types import SimpleNamespace

import pytest

from app.models.article import Article
from app.models.source import NewsSource
from app.models.llm import LLMConfig


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value.encode() if isinstance(value, str) else value

    def delete(self, key):
        self.values.pop(key, None)


class Provider:
    def __init__(self):
        self.calls = []
        self.reply = 'Translated text'
        self.error = None
        self.before = None
        self.finish_reason = 'stop'

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.before:
            self.before(kwargs)
        if self.error:
            raise self.error
        content = self.reply(kwargs) if callable(self.reply) else self.reply
        if not isinstance(content, str) and content is not None:
            content = json.dumps(content)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=self.finish_reason)],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


@pytest.fixture
def llm_env(db, monkeypatch):
    import app.llm.client as client_module
    import app.llm.circuit_breaker as breaker_module
    cache, provider = MemoryRedis(), Provider()
    monkeypatch.setattr(client_module, 'redis_client', cache)
    monkeypatch.setattr(breaker_module, 'redis_client', cache)
    monkeypatch.setattr(client_module.litellm, 'completion', provider)
    config = LLMConfig(provider='synthetic', model='primary', is_default=True,
                       tasks=['translate', 'digest', 'summarize', 'ner', 'sentiment', 'classify', 'insight'],
                       cost_per_1k_input='0.01', cost_per_1k_output='0.02')
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
    db.session.add_all([config, source])
    db.session.flush()
    article = Article(source_id=source.id, url='https://test.invalid/a', title_fr='French title',
                      content_fr='A synthetic report about Grenoble research.')
    db.session.add(article)
    db.session.commit()
    return SimpleNamespace(provider=provider, cache=cache, config=config, article=article)
