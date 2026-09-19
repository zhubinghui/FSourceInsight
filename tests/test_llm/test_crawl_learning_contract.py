"""Public learning task facade must never accept an unauthenticated cache hit."""
import json
import pytest
from app.llm.client import LLMClient
from app.llm.budget import BudgetError
from tests.test_web.test_crawl_config import recipe_for
from tests.test_web.test_crawl_learning import learning_io, model


def test_crawl_task_requires_persisted_attempt_even_when_cache_contains_recipe(model, monkeypatch):
    monkeypatch.setattr(model.cache, 'get', lambda key: json.dumps(recipe_for(1)) if key.startswith('llm_cache:') else None)
    with pytest.raises(BudgetError, match='Persisted learning attempt required'):
        LLMClient().propose_crawl_recipe(None, [])
    assert not model.provider.calls
