"""Crawl run control and the article LLM outbox (M2). Control state lives in MySQL, never Redis."""
from app.extensions import db


class CrawlSourceState(db.Model):
    """One row per news source: next due time, failure streak, attention and the run lease."""
    __tablename__ = 'crawl_source_state'

    source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), primary_key=True)
    next_due_at = db.Column(db.DateTime, nullable=False)
    due_reason = db.Column(db.String(16), nullable=False)
    consecutive_failures = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    attention_reason = db.Column(db.String(40))
    attention_since = db.Column(db.DateTime)
    claim_id = db.Column(db.String(36))
    lease_expires_at = db.Column(db.DateTime)
    # Monotonic: every claim increments it, so a late worker can never commit.
    fence = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    running_log_id = db.Column(db.Integer, db.ForeignKey('crawl_log.id'))

    __table_args__ = (db.Index('idx_crawl_state_due', 'next_due_at'),)


class CrawlSchemaDecision(db.Model):
    """Append-only human decision about which recipe scheduled crawls use."""
    __tablename__ = 'crawl_schema_decision'

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('crawl_source_profile.id'), nullable=False)
    action = db.Column(db.String(16), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'))
    from_version_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'))
    activation_generation = db.Column(db.Integer, nullable=False)
    evidence_kind = db.Column(db.String(16))
    evidence_ref = db.Column(db.String(64))
    evidence_hash = db.Column(db.String(64))
    source_generation = db.Column(db.Integer, nullable=False)
    policy_version_id = db.Column(db.Integer, db.ForeignKey('crawl_policy_version.id'))
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (db.Index('idx_schema_decision_profile', 'profile_id', 'id'),)


class ArticleLLMJob(db.Model):
    """Durable LLM work for one article, created in the same transaction as the article."""
    __tablename__ = 'article_llm_job'

    id = db.Column(db.String(36), primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='SET NULL'), index=True)
    # Equals article_id only while queued/running: at most one active job per article.
    active_article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='SET NULL'), unique=True)
    trigger = db.Column(db.String(16), nullable=False)
    crawl_log_id = db.Column(db.Integer, db.ForeignKey('crawl_log.id'))
    force = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    state = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(80))
    claim_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    deadline_at = db.Column(db.DateTime)
    next_dispatch_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime)

    __table_args__ = (db.Index('idx_article_llm_job_pending', 'state', 'next_dispatch_at'),)
