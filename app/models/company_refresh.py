"""Durable refresh intent for companies that already have an analysis."""
from app.extensions import db


class CompanyRefreshJob(db.Model):
    __tablename__ = 'company_refresh_job'

    id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id', ondelete='SET NULL'), index=True)
    # Equals company_id only while queued/running: at most one active job per
    # company. Closing a job clears it; deleting the company releases it.
    active_company_id = db.Column(db.Integer, db.ForeignKey('company.id', ondelete='SET NULL'), unique=True)
    trigger = db.Column(db.String(16), nullable=False)
    trigger_ref = db.Column(db.String(80))
    protocol = db.Column(db.String(40), nullable=False)
    # Recorded at claim: later company changes make the result stale.
    company_generation = db.Column(db.Integer)
    prompt_hash = db.Column(db.String(64))
    state = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(80))
    claim_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    deadline_at = db.Column(db.DateTime)
    next_dispatch_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime)
    __table_args__ = (db.Index('idx_company_refresh_pending', 'state', 'next_dispatch_at'),)
