import hashlib
import json
import logging
import os
import time
import litellm
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.extensions import db, redis_client
from app.models.llm import LLMConfig, LLMUsageLog
from app.llm import prompts, budget as spend
from app.llm.circuit_breaker import CircuitBreaker
from app.llm.routing import ordered_configs
from app.llm.contracts import CONTRACT_VERSION, JSON_TASKS, InvalidLLMResponse, validate_response
from app.utils.text import strip_html

logger = logging.getLogger(__name__)
CACHE_TTL = 7 * 24 * 3600
MAX_ATTEMPTS = 3
MAX_INPUT_CHARS = {
    'translate': 50000, 'digest': 50000, 'summarize': 30000,
    'ner': 20000, 'sentiment': 20000, 'classify': 20000, 'insight': 30000,
}
DEFAULT_MAX_INPUT_CHARS = 30000


def _service_tier(config):
    # Explicit global OpenAI endpoint opts into standard prices, not Project auto/Fast.
    # Do not send OpenAI-specific options to custom gateways or other providers.
    if (config.provider == 'openai' and ('/' not in config.model or config.model.startswith('openai/'))
            and (config.api_base_url or '').rstrip('/') == 'https://api.openai.com/v1'):
        return 'default'
    return None


class _ProviderFailure(Exception):
    """A logged provider/contract failure, eligible for bounded fallback."""
    def __init__(self, error):
        self.error = error
        super().__init__(type(error).__name__)


class LLMClient:
    """Task facade with strict contracts, versioned cache and independent usage.

    Callers must not hold flushed business write locks across a model call.
    Pending objects are never autoflushed or committed by this client. Article
    processing collects results first (pipeline.py). A database reservation is
    committed before each paid attempt. Accounting failures abort without fallback.
    """
    def __init__(self):
        self._breaker = CircuitBreaker()
        # Actual successful route (including cache hits), not a fresh estimate.
        self.routes = {}

    def _candidates(self, task_type):
        with Session(db.engine) as session:
            configs = session.query(LLMConfig).filter_by(is_active=True).all()
        return ordered_configs(configs, task_type)

    def _get_config(self, task_type):
        return next((c for c in self._candidates(task_type) if not self._breaker.is_open(c.provider)), None)

    @staticmethod
    def _cache_key(task_type, messages, config):
        # Effective input includes every title/context/lang/prompt actually sent.
        # Credentials are deliberately absent; endpoint/model/params are included.
        payload = {
            'task': task_type, 'messages': messages, 'prompt_version': prompts.PROMPT_VERSION,
            'contract_version': CONTRACT_VERSION, 'config_id': config.id,
            'provider': config.provider, 'model': config.model, 'endpoint': config.api_base_url,
            'max_tokens': config.max_tokens if config.max_tokens is not None else 4096,
            'temperature': config.temperature if config.temperature is not None else 0.3,
            'response_format': 'json_object' if task_type in JSON_TASKS else 'text',
        }
        tier = _service_tier(config)
        if tier is not None:
            payload['service_tier'] = tier
        content = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        return 'llm_cache:v2:' + hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def _get_cached(key, task):
        try:
            cached = redis_client.get(key) if redis_client else None
            if cached is not None:
                text = cached.decode('utf-8') if isinstance(cached, bytes) else cached
                return validate_response(task, text)
        except (RedisError, UnicodeError, InvalidLLMResponse):
            logger.warning('Ignoring unavailable or invalid LLM response cache')
        return None

    @staticmethod
    def _set_cache(key, value, task):
        try:
            if redis_client:
                text = json.dumps(value, ensure_ascii=False, allow_nan=False) if task in JSON_TASKS else value
                redis_client.setex(key, CACHE_TTL, text.encode('utf-8'))
        except RedisError:
            logger.warning('LLM response cache write unavailable; paid result retained')

    def _call_llm(self, config, messages, task_type, article_id, learning_attempt=None, discovery_job=None,
                  refresh_job=None):
        model = config.model
        if config.provider and '/' not in model:
            model = f'{config.provider}/{model}'
        kwargs = {
            'model': model, 'messages': messages, 'num_retries': 0, 'timeout': 60,
            'max_tokens': config.max_tokens if config.max_tokens is not None else 4096,
            'temperature': config.temperature if config.temperature is not None else 0.3,
        }
        key = os.environ.get(config.api_key_env_var) if config.api_key_env_var else None
        if key:
            kwargs['api_key'] = key
        if config.api_base_url:
            kwargs['api_base'] = config.api_base_url
        tier = _service_tier(config)
        if tier is not None:
            kwargs['service_tier'] = tier
        if task_type in JSON_TASKS:
            kwargs['response_format'] = {'type': 'json_object'}
        permit = spend.reserve(config, task_type, learning_attempt, messages, discovery_job=discovery_job,
                               refresh_job=refresh_job)
        start = time.monotonic()
        usage, error, result = None, None, None
        try:
            response = litellm.completion(**kwargs)
            usage = response.usage
            if response.choices[0].finish_reason != 'stop':
                raise InvalidLLMResponse('LLM response did not complete normally')
            result = validate_response(task_type, response.choices[0].message.content)
        except Exception as exc:
            error = exc
        log_entry = LLMUsageLog(
            config_id=config.id, task_type=task_type, article_id=article_id,
            latency_ms=int((time.monotonic() - start) * 1000), success=error is None,
            error_message=type(error).__name__ if error else None,
        )
        # Outside the provider exception handler: failed settlement retains the
        # committed permit and must never cause another billable call.
        accounting_error = spend.settle(permit, log_entry, usage)
        if accounting_error and (error is None or usage is not None or learning_attempt is not None
                                 or discovery_job is not None or refresh_job is not None):
            raise accounting_error
        if error is not None:
            self._breaker.record_failure(config.provider)
            raise _ProviderFailure(error)
        self._breaker.record_success(config.provider)
        return result

    def _request(self, task, messages, article_id=None, learning_attempt=None, discovery_job=None, refresh_job=None):
        last_error, attempts = None, 0
        for config in self._candidates(task):
            if self._breaker.is_open(config.provider):
                continue
            key = self._cache_key(task, messages, config)
            result = self._get_cached(key, task) if learning_attempt is None else None
            if result is None:
                if attempts >= MAX_ATTEMPTS:
                    break
                attempts += 1
                try:
                    result = self._call_llm(config, messages, task, article_id, learning_attempt, discovery_job,
                                           refresh_job)
                except _ProviderFailure as exc:
                    last_error = exc.error
                    continue
                if learning_attempt is None:
                    self._set_cache(key, result, task)
            self.routes[task] = {'provider': config.provider, 'model': config.model}
            return result
        if last_error:
            raise last_error
        raise RuntimeError(f'No available LLM config for {task} task')

    @staticmethod
    def _prepare(text, task):
        text = strip_html(text) or text
        return text[:MAX_INPUT_CHARS.get(task, DEFAULT_MAX_INPUT_CHARS)]

    def propose_crawl_recipe(self, attempt_id, messages):
        """Only a persisted, currently claimed learning attempt may pay for this task."""
        if not isinstance(attempt_id, str) or not attempt_id:
            raise spend.BudgetError('Persisted learning attempt required')
        return self._request('crawl_schema', messages, learning_attempt=attempt_id)

    def translate(self, text, target_lang='zh', article_id=None):
        return self._request('translate', prompts.get_translate_messages(
            self._prepare(text, 'translate'), target_lang), article_id)

    def summarize(self, text, target_lang='zh', article_id=None):
        return self._request('summarize', prompts.get_summarize_messages(
            self._prepare(text, 'summarize'), target_lang), article_id)

    def digest(self, title, text, target_lang='zh', article_id=None):
        return self._request('digest', prompts.get_digest_messages(
            strip_html(title) or title, self._prepare(text, 'digest'), target_lang), article_id)

    def extract_companies(self, text, article_id=None):
        return self._request('ner', prompts.get_ner_messages(self._prepare(text, 'ner')), article_id)['companies']

    def analyze_sentiment(self, text, company_name, article_id=None):
        return self._request('sentiment', prompts.get_sentiment_messages(
            self._prepare(text, 'sentiment'), company_name), article_id)

    def classify_category(self, text, article_id=None):
        return self._request('classify', prompts.get_classify_messages(self._prepare(text, 'classify')), article_id)

    def generate_insight(self, title, text, target_lang='zh', article_id=None):
        return self._request('insight', prompts.get_insight_messages(
            strip_html(title) or title, self._prepare(text, 'insight'), target_lang), article_id)

    def analyze_company(self, name, sector=None, headquarters=None, description=None,
                        spinoff_origin=None, company_stage=None, recent_news=None, website_excerpt=None,
                        discovery_job=None, refresh_job=None):
        messages = prompts.get_company_analysis_messages(
            name, sector, headquarters, description, spinoff_origin, company_stage,
            recent_news, website_excerpt=website_excerpt)
        if refresh_job is not None:
            if discovery_job is not None or not isinstance(refresh_job, str) or not refresh_job:
                raise spend.BudgetError('Persisted company refresh job required')
            from app.llm.company_refresh import check as check_refresh
            check_refresh(refresh_job, messages)  # Cache hits also require the current claim.
            return self._request('company_analysis', messages, refresh_job=refresh_job)
        if discovery_job is not None:
            if not isinstance(discovery_job, str) or not discovery_job:
                raise spend.BudgetError('Persisted discovery job required')
            from app.llm.startup_analysis import check
            check(discovery_job, messages)  # Cache hits also require current ownership/input.
        return self._request('company_analysis', messages, discovery_job=discovery_job)
