"""Durable initial analysis intent; no historical ownership is backfilled."""
from sqlalchemy import event, inspect

from app.extensions import db
from .company import Company
from .startup_source import StartupSource


class StartupAnalysisJob(db.Model):
    __tablename__ = 'startup_analysis_job'

    id = db.Column(db.String(36), primary_key=True)
    # Delete the business row without deleting evidence or assigning its job to
    # a subsequently reused id. Original ids remain in the immutable input.
    company_id = db.Column(db.Integer, db.ForeignKey('company.id', ondelete='SET NULL'), unique=True)
    source_id = db.Column(db.Integer, db.ForeignKey('startup_source.id', ondelete='SET NULL'))
    protocol = db.Column(db.String(40), nullable=False)
    inputs = db.Column(db.JSON, nullable=False)
    input_hash = db.Column(db.String(64), nullable=False)
    prompt_hash = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(80))
    claim_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    deadline_at = db.Column(db.DateTime)
    next_dispatch_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime)
    __table_args__ = (
        db.Index('idx_startup_analysis_pending', 'state', 'next_dispatch_at'),
        db.Index('idx_startup_analysis_source', 'source_id', 'created_at'),
    )


@event.listens_for(StartupSource, 'before_update')
def source_generation(mapper, connection, target):
    if any(inspect(target).attrs[key].history.has_changes()
           for key in ('url', 'source_type', 'is_active')):
        # SQL expression increments the current DB value, not a stale ORM copy.
        target.analysis_generation = StartupSource.analysis_generation + 1


@event.listens_for(Company, 'before_update')
def company_generation(mapper, connection, target):
    if any(inspect(target).attrs[key].history.has_changes() for key in (
            'name', 'slug', 'aliases', 'description', 'website', 'headquarters',
            'is_grenoble', 'sector', 'company_stage', 'spinoff_origin',
            'is_auto_created', 'ai_analysis', 'ai_analysis_at', 'ai_revision_history',
            'review_status', 'entity_type', 'postcode', 'city', 'local_site')):
        target.analysis_generation = Company.analysis_generation + 1
