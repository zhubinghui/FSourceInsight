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
    # Compatibility defaults preserve existing cost/id order until an admin edits it.
    role = db.Column(db.String(16), nullable=False, default='primary', server_default='primary')
    priority = db.Column(db.Integer, nullable=False, default=100, server_default='100')
    max_tokens = db.Column(db.Integer, default=4096)
    temperature = db.Column(db.Float, default=0.3)
    cost_per_1k_input = db.Column(db.Numeric(10, 6))
    cost_per_1k_output = db.Column(db.Numeric(10, 6))
    # Admin-attested total BILLABLE token ceilings, including hidden/reasoning
    # tokens. NULL means unreviewed, never infer a bound from a tokenizer estimate.
    billing_input_limit = db.Column(db.Integer)
    billing_output_limit = db.Column(db.Integer)
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


class LLMBudgetGate(db.Model):
    """One database mutex, not an evictable cache lock or a spend counter."""
    __tablename__ = 'llm_budget_gate'
    id = db.Column(db.Integer, primary_key=True)


class LLMReservation(db.Model):
    """A committed permit precedes each external attempt; no prompt or secrets."""
    __tablename__ = 'llm_reservation'
    id = db.Column(db.String(36), primary_key=True)
    config_id = db.Column(db.Integer, db.ForeignKey('llm_config.id'), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    learning_attempt_id = db.Column(db.String(36), db.ForeignKey('crawl_repair_attempt.id'))
    startup_analysis_id = db.Column(db.String(36), db.ForeignKey('startup_analysis_job.id'), index=True)
    billing_day = db.Column(db.Date, nullable=False)
    provider = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(200), nullable=False)
    endpoint_hash = db.Column(db.String(64), nullable=False)
    input_limit = db.Column(db.Integer, nullable=False)
    output_limit = db.Column(db.Integer, nullable=False)
    input_price = db.Column(db.Numeric(10, 6), nullable=False)
    output_price = db.Column(db.Numeric(10, 6), nullable=False)
    reserved_usd = db.Column(db.Numeric(18, 6), nullable=False)
    actual_usd = db.Column(db.Numeric(18, 6))
    state = db.Column(db.String(16), nullable=False)
    usage_id = db.Column(db.Integer, db.ForeignKey('llm_usage_log.id'), unique=True)
    created_at = db.Column(db.DateTime, nullable=False)
    settled_at = db.Column(db.DateTime)
    reconciliation = db.relationship('LLMReconciliation', uselist=False, lazy='joined')
    __table_args__ = (db.Index('idx_llm_reservation_day_state', 'billing_day', 'state'),)


class LLMReconciliation(db.Model):
    """One immutable operator decision; original supplier usage is retained."""
    __tablename__ = 'llm_reconciliation'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.String(36), db.ForeignKey('llm_reservation.id'), nullable=False, unique=True)
    final_cost = db.Column(db.Numeric(18, 6), nullable=False)
    evidence_note = db.Column(db.String(500), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
