from datetime import datetime
from app.extensions import db


class LLMConfig(db.Model):
    __tablename__ = 'llm_config'

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(100), nullable=False)  # openai, anthropic, ollama...
    model = db.Column(db.String(200), nullable=False)  # gpt-4o, claude-sonnet-4-20250514...
    api_key_env_var = db.Column(db.String(200))  # Env var name, never store key in DB
    api_base_url = db.Column(db.String(500))  # For custom endpoints / Ollama
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    max_tokens = db.Column(db.Integer, default=4096)
    temperature = db.Column(db.Float, default=0.3)
    cost_per_1k_input = db.Column(db.Numeric(10, 6))
    cost_per_1k_output = db.Column(db.Numeric(10, 6))
    tasks = db.Column(db.JSON)  # ["translate", "summarize", "ner", "sentiment", "classify"]
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    usage_logs = db.relationship('LLMUsageLog', backref='config', lazy='dynamic')

    def __repr__(self):
        return f'<LLMConfig {self.provider}/{self.model}>'


class LLMUsageLog(db.Model):
    __tablename__ = 'llm_usage_log'

    id = db.Column(db.Integer, primary_key=True)
    config_id = db.Column(db.Integer, db.ForeignKey('llm_config.id'), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    article_id = db.Column(
        db.Integer, db.ForeignKey('article.id', ondelete='SET NULL')
    )
    input_tokens = db.Column(db.Integer)
    output_tokens = db.Column(db.Integer)
    cost_usd = db.Column(db.Numeric(10, 6))
    latency_ms = db.Column(db.Integer)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_llm_usage_created', 'created_at'),
        db.Index('idx_llm_usage_task', 'task_type', 'created_at'),
    )

    def __repr__(self):
        return f'<LLMUsageLog {self.task_type} config={self.config_id}>'
