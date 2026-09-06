"""Seed the database with default LLM configurations.

Mixed-provider strategy for cost optimisation:
  - DeepSeek: bulk tasks (translate, digest, summarize, sentiment) — cheapest
  - OpenAI gpt-5.4-mini: structured output tasks (NER, classify, insight)
  - OpenAI gpt-5.4-nano: ultra-cheap fallback for simple tasks
  - Anthropic Claude: premium option, disabled by default

Routing uses role (primary before fallback), then priority, input cost, DB id.
Only NEW records get these defaults; existing administrator choices are untouched.

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
        'role': 'primary', 'priority': 100,
        'tasks': ['translate', 'digest', 'summarize', 'sentiment'],
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
        'role': 'primary', 'priority': 100,
        'tasks': ['ner', 'classify', 'insight', 'company_analysis'],
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
        'role': 'fallback', 'priority': 100,
        'tasks': ['translate', 'digest', 'summarize', 'ner', 'classify', 'sentiment', 'insight', 'company_analysis'],
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
        'role': 'fallback', 'priority': 200,
        'tasks': ['translate', 'summarize', 'digest', 'ner', 'insight', 'company_analysis'],
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
