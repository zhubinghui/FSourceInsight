import hashlib
import json
import logging
import os
import time
from typing import Optional

import litellm
from app.extensions import db, redis_client
from app.models.llm import LLMConfig, LLMUsageLog
from app.llm.prompts import (
    get_translate_messages, get_summarize_messages,
    get_ner_messages, get_sentiment_messages, get_classify_messages,
)
from app.llm.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

CACHE_TTL = 7 * 24 * 3600  # 7 days


class LLMClient:
    """Facade for all LLM operations. Routes to the correct provider via LiteLLM.

    Features:
    - Multi-provider support via LiteLLM
    - Redis response caching
    - Usage/cost tracking to DB
    - Per-provider circuit breaker with automatic fallback
    """

    def __init__(self):
        self._breaker = CircuitBreaker()

    # ── Config resolution ─────────────────────────────────────────

    def _get_config(self, task_type: str) -> Optional[LLMConfig]:
        """Get the active LLM config for a specific task type."""
        configs = LLMConfig.query.filter_by(is_active=True).all()
        for config in configs:
            if config.tasks and task_type in config.tasks:
                if not self._breaker.is_open(config.provider):
                    return config
        # Fall back to default (even if breaker is open — last resort)
        return LLMConfig.query.filter_by(is_active=True, is_default=True).first()

    def _get_fallback_config(self, failed_config: LLMConfig,
                              task_type: str) -> Optional[LLMConfig]:
        """Get an alternative config after the primary one fails."""
        configs = LLMConfig.query.filter_by(is_active=True).all()
        for config in configs:
            if config.id == failed_config.id:
                continue
            if config.tasks and task_type in config.tasks:
                if not self._breaker.is_open(config.provider):
                    return config
        # Try default as last resort
        default = LLMConfig.query.filter_by(
            is_active=True, is_default=True
        ).first()
        if default and default.id != failed_config.id:
            return default
        return None

    def _get_api_key(self, config: LLMConfig) -> Optional[str]:
        if config.api_key_env_var:
            return os.environ.get(config.api_key_env_var)
        return None

    # ── Budget ────────────────────────────────────────────────────

    def _check_daily_budget(self):
        """Raise if today's LLM spending has exceeded the configured daily budget."""
        from flask import current_app
        from datetime import datetime
        from sqlalchemy import func

        budget = current_app.config.get('LLM_DAILY_BUDGET_USD', 0)
        if not budget or budget <= 0:
            return  # Unlimited

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_cost = db.session.query(
            func.coalesce(func.sum(LLMUsageLog.cost_usd), 0)
        ).filter(LLMUsageLog.created_at >= today).scalar()

        if float(today_cost or 0) >= budget:
            raise RuntimeError(
                f'Daily LLM budget exceeded: ${float(today_cost):.4f} / ${budget:.2f}. '
                f'Increase LLM_DAILY_BUDGET_USD or wait until tomorrow.'
            )

    # ── Cache ─────────────────────────────────────────────────────

    def _cache_key(self, task_type: str, text: str, **kwargs) -> str:
        content = f'{task_type}:{text}:{json.dumps(kwargs, sort_keys=True)}'
        return f'llm_cache:{hashlib.sha256(content.encode()).hexdigest()}'

    def _get_cached(self, cache_key: str) -> Optional[str]:
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                return cached.decode('utf-8')
        return None

    def _set_cache(self, cache_key: str, value: str):
        if redis_client:
            redis_client.setex(cache_key, CACHE_TTL, value.encode('utf-8'))

    # ── Core LLM call ────────────────────────────────────────────

    def _call_llm(self, config: LLMConfig, messages: list[dict],
                   task_type: str, article_id: int = None,
                   response_format: dict = None) -> str:
        """Make an LLM API call with usage tracking and circuit breaker."""
        api_key = self._get_api_key(config)
        model = config.model
        if config.provider and '/' not in model:
            model = f'{config.provider}/{config.model}'

        kwargs = {
            'model': model,
            'messages': messages,
            'max_tokens': config.max_tokens or 4096,
            'temperature': config.temperature or 0.3,
        }
        if api_key:
            kwargs['api_key'] = api_key
        if config.api_base_url:
            kwargs['api_base'] = config.api_base_url
        if response_format:
            kwargs['response_format'] = response_format

        start = time.time()
        try:
            response = litellm.completion(**kwargs)
            latency_ms = int((time.time() - start) * 1000)

            result = response.choices[0].message.content
            usage = response.usage

            # Record success for circuit breaker
            self._breaker.record_success(config.provider)

            # Log usage
            log_entry = LLMUsageLog(
                config_id=config.id,
                task_type=task_type,
                article_id=article_id,
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
                latency_ms=latency_ms,
                success=True,
            )
            if usage and config.cost_per_1k_input and config.cost_per_1k_output:
                cost = (
                    float(config.cost_per_1k_input) * usage.prompt_tokens / 1000
                    + float(config.cost_per_1k_output) * usage.completion_tokens / 1000
                )
                log_entry.cost_usd = cost

            db.session.add(log_entry)
            db.session.commit()
            return result

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            self._breaker.record_failure(config.provider)

            log_entry = LLMUsageLog(
                config_id=config.id,
                task_type=task_type,
                article_id=article_id,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e),
            )
            db.session.add(log_entry)
            db.session.commit()

            # Try fallback provider
            fallback = self._get_fallback_config(config, task_type)
            if fallback:
                logger.warning(
                    f'{config.provider} failed for {task_type}, '
                    f'falling back to {fallback.provider}/{fallback.model}'
                )
                return self._call_llm(
                    fallback, messages, task_type, article_id, response_format
                )
            raise

    def _call_with_cache(self, task_type: str, messages: list[dict],
                          cache_key: str, article_id: int = None,
                          response_format: dict = None,
                          parse_json: bool = False) -> str | list | dict:
        """Common pattern: check cache → check budget → call LLM → store cache."""
        cached = self._get_cached(cache_key)
        if cached:
            return json.loads(cached) if parse_json else cached

        # Check daily cost budget before making API call
        try:
            self._check_daily_budget()
        except RuntimeError as e:
            logger.warning(str(e))
            raise

        config = self._get_config(task_type)
        if not config:
            raise RuntimeError(f'No LLM config found for {task_type} task')

        result = self._call_llm(
            config, messages, task_type, article_id, response_format
        )

        if parse_json:
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                logger.warning(f'Failed to parse {task_type} response as JSON')
                parsed = self._json_fallback(task_type)
            self._set_cache(cache_key, json.dumps(parsed))
            return parsed
        else:
            self._set_cache(cache_key, result)
            return result

    @staticmethod
    def _json_fallback(task_type: str):
        """Return safe default when JSON parsing fails."""
        if task_type == 'sentiment':
            return {'sentiment': 'neutral', 'score': 0.0, 'reason': 'parse_error'}
        return []  # ner, classify

    # ── Public API ───────────────────────────────────────────────

    def translate(self, text: str, target_lang: str = 'zh',
                  article_id: int = None) -> str:
        """Translate French text to target language."""
        cache_key = self._cache_key('translate', text, target_lang=target_lang)
        messages = get_translate_messages(text, target_lang)
        return self._call_with_cache('translate', messages, cache_key, article_id)

    def summarize(self, text: str, target_lang: str = 'zh',
                  article_id: int = None) -> str:
        """Generate a concise summary of the article."""
        cache_key = self._cache_key('summarize', text, target_lang=target_lang)
        messages = get_summarize_messages(text, target_lang)
        return self._call_with_cache('summarize', messages, cache_key, article_id)

    def extract_companies(self, text: str, article_id: int = None) -> list[dict]:
        """Extract company/organization names from French text using NER."""
        cache_key = self._cache_key('ner', text)
        messages = get_ner_messages(text)
        result = self._call_with_cache(
            'ner', messages, cache_key, article_id,
            response_format={'type': 'json_object'}, parse_json=True
        )
        # Normalize: extract 'companies' key if wrapped
        if isinstance(result, dict) and 'companies' in result:
            return result['companies']
        if isinstance(result, list):
            return result
        return []

    def analyze_sentiment(self, text: str, company_name: str,
                          article_id: int = None) -> dict:
        """Analyze sentiment of the article toward a specific company."""
        cache_key = self._cache_key('sentiment', text, company=company_name)
        messages = get_sentiment_messages(text, company_name)
        return self._call_with_cache(
            'sentiment', messages, cache_key, article_id,
            response_format={'type': 'json_object'}, parse_json=True
        )

    def classify_category(self, text: str, article_id: int = None) -> list[dict]:
        """Classify the article into tech categories."""
        cache_key = self._cache_key('classify', text)
        messages = get_classify_messages(text)
        result = self._call_with_cache(
            'classify', messages, cache_key, article_id,
            response_format={'type': 'json_object'}, parse_json=True
        )
        # Normalize: extract 'categories' key if wrapped
        if isinstance(result, dict) and 'categories' in result:
            return result['categories']
        if isinstance(result, list):
            return result
        return []
