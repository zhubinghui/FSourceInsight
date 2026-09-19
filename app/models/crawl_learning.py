"""Durable learning identity; neither a publication nor validation decision."""
from app.extensions import db


class CrawlRepairSession(db.Model):
    __tablename__ = 'crawl_repair_session'
    id = db.Column(db.String(36), primary_key=True)
    history_sequence = db.Column(db.Integer, unique=True)
    input_hash = db.Column(db.String(64))
    source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), nullable=False)
    base_version_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'), nullable=False)
    capture_id = db.Column(db.Integer, db.ForeignKey('crawl_capture_manifest.id'), nullable=False, unique=True)
    evidence = db.Column(db.JSON, nullable=False)
    protocol_version = db.Column(db.String(40), nullable=False)
    state = db.Column(db.String(24), nullable=False)
    reason = db.Column(db.String(80))
    rounds = db.Column(db.Integer, nullable=False, default=0)
    max_rounds = db.Column(db.Integer, nullable=False, default=3)
    cost_limit = db.Column(db.Numeric(18, 6), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    deadline_at = db.Column(db.DateTime, nullable=False)
    cooldown_until = db.Column(db.DateTime)
    retry_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    # NULL on historical/old-writer rows; never silently enable their dispatch.
    dispatch_due_at = db.Column(db.DateTime)
    __table_args__ = (db.Index('idx_repair_source_state', 'source_id', 'state'),
                      db.Index('idx_repair_dispatch_due', 'state', 'dispatch_due_at'))


class CrawlRepairAttempt(db.Model):
    __tablename__ = 'crawl_repair_attempt'
    id = db.Column(db.String(36), primary_key=True)
    exposure_sequence = db.Column(db.Integer, unique=True)
    exposure_hash = db.Column(db.String(64))
    session_id = db.Column(db.String(36), db.ForeignKey('crawl_repair_session.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    state = db.Column(db.String(24), nullable=False)
    # Conservative may-have-been-sent record committed BEFORE any model call.
    exposure = db.Column(db.JSON, nullable=False)
    prompt_hash = db.Column(db.String(64), nullable=False)
    recipe_hash = db.Column(db.String(64))
    feedback = db.Column(db.JSON)
    candidate_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'))
    created_at = db.Column(db.DateTime, nullable=False)
    __table_args__ = (db.UniqueConstraint('session_id', 'number', name='uq_repair_attempt_number'),)


class CrawlRepairRetry(db.Model):
    """Append-only administrator request; never a new budget or deadline."""
    __tablename__ = 'crawl_repair_retry'
    id = db.Column(db.String(36), primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey('crawl_repair_session.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    after_round = db.Column(db.Integer, nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False)
    note = db.Column(db.String(300), nullable=False)
    document_hash = db.Column(db.String(64), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('session_id', 'number', name='uq_repair_retry_number'),
        db.UniqueConstraint('session_id', 'after_round', name='uq_repair_retry_round'),
    )


class CrawlValidationReport(db.Model):
    """One frozen candidate and one system-selected holdout, never publication."""
    __tablename__ = 'crawl_validation_report'
    id = db.Column(db.String(36), primary_key=True)
    session_id = db.Column(db.String(36), db.ForeignKey('crawl_repair_session.id'), nullable=False, unique=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'), nullable=False, unique=True)
    capture_id = db.Column(db.Integer, db.ForeignKey('crawl_capture_manifest.id'))
    binding = db.Column(db.JSON, nullable=False)
    binding_hash = db.Column(db.String(64), nullable=False)
    selection = db.Column(db.JSON)
    selection_hash = db.Column(db.String(64))
    state = db.Column(db.String(24), nullable=False)
    result = db.Column(db.JSON)
    result_hash = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    deadline_at = db.Column(db.DateTime)
    __table_args__ = (db.Index('idx_validation_state_deadline', 'state', 'deadline_at'),)


class CrawlLearningHistory(db.Model):
    """Workflow coverage marker. No retroactive certification of old records."""
    __tablename__ = 'crawl_learning_history'
    id = db.Column(db.Integer, primary_key=True)
    session_generation = db.Column(db.Integer, nullable=False)
    exposure_generation = db.Column(db.Integer, nullable=False)
    selection_generation = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    history_complete = db.Column(db.Boolean, nullable=False)
