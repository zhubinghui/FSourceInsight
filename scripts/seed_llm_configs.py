"""Seed the database with default LLM configurations.

Mixed-provider strategy for cost optimisation:
  - DeepSeek: bulk tasks (translate, digest, summarize, sentiment) — cheapest
  - OpenAI gpt-5.4-mini: structured output tasks (NER, classify, insight)
  - OpenAI gpt-5.4-nano: ultra-cheap fallback for simple tasks
  - Anthropic Claude: premium option, disabled by default

Cost-aware routing in LLMClient picks the cheapest active config per task.
Seed order (= DB id) is the tiebreaker.

API keys must be set as environment variables — never stored in DB.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.llm import LLMConfig

CONFIGS = [
    # ── DeepSeek: primary for high-volume tasks (cheapest) ───────
    # Input: $0.14/M tokens, Output: $0.28/M tokens
    {
        'provider': 'deepseek',
        'model': 'deepseek-chat',
        'api_key_env_var': 'DEEPSEEK_API_KEY',
        'is_default': False,
        'is_active': True,
        'max_tokens': 4096,
        'temperature': 0.3,
        'cost_per_1k_input': 0.00014,
        'cost_per_1k_output': 0.00028,
        'tasks': ['translate', 'digest', 'summarize', 'sentiment', 'insight'],
    },
    # ── OpenAI gpt-5.4-mini: structured output + analysis ───────
    # Input: $2.50/M tokens, Output: $10.00/M tokens
    # Better JSON compliance for NER/classify; deeper reasoning for insight.
    {
        'provider': 'openai',
        'model': 'gpt-5.4-mini',
        'api_key_env_var': 'OPENAI_API_KEY',
        'is_default': True,
        'is_active': True,
        'max_tokens': 4096,
        'temperature': 0.3,
        'cost_per_1k_input': 0.0025,
        'cost_per_1k_output': 0.01,
        'tasks': ['ner', 'classify', 'insight'],
    },
    # ── OpenAI gpt-5.4-nano: ultra-cheap fallback ───────────────
    # Input: $0.15/M tokens, Output: $0.60/M tokens
    # Activated as a backup when DeepSeek or gpt-5.4-mini is down.
    {
        'provider': 'openai',
        'model': 'gpt-5.4-nano',
        'api_key_env_var': 'OPENAI_API_KEY',
        'is_default': False,
        'is_active': True,
        'max_tokens': 4096,
        'temperature': 0.3,
        'cost_per_1k_input': 0.00015,
        'cost_per_1k_output': 0.0006,
        'tasks': ['translate', 'summarize', 'ner', 'classify', 'sentiment', 'insight'],
    },
    # ── Anthropic Claude: premium option (disabled by default) ──
    # Enable via Admin UI when you need highest-quality insight.
    {
        'provider': 'anthropic',
        'model': 'claude-sonnet-4-20250514',
        'api_key_env_var': 'ANTHROPIC_API_KEY',
        'is_default': False,
        'is_active': False,
        'max_tokens': 4096,
        'temperature': 0.3,
        'cost_per_1k_input': 0.003,
        'cost_per_1k_output': 0.015,
        'tasks': ['translate', 'summarize', 'digest', 'ner', 'insight'],
    },
]


def seed():
    app = create_app()
    with app.app_context():
        for data in CONFIGS:
            existing = LLMConfig.query.filter_by(
                provider=data['provider'], model=data['model']
            ).first()
            if existing:
                print(f'  Skipping {data["provider"]}/{data["model"]} (already exists)')
                continue
            config = LLMConfig(**data)
            db.session.add(config)
            print(f'  Added: {data["provider"]}/{data["model"]}')
        db.session.commit()
        print(f'\nDone. {LLMConfig.query.count()} LLM configs in database.')


if __name__ == '__main__':
    seed()
