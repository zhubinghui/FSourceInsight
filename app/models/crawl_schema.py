"""Draft storage. Recipe validity is not network authority or publication."""
from datetime import datetime

from app.extensions import db


class CrawlSourceProfile(db.Model):
    __tablename__ = 'crawl_source_profile'

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), nullable=False)
    generation = db.Column(db.Integer, nullable=False, default=0)
    source_generation = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    policy_generation = db.Column(db.Integer, nullable=True)

    __table_args__ = (db.UniqueConstraint('source_id', name='uq_crawl_profile_source'),)


class CrawlPolicyVersion(db.Model):
    __tablename__ = 'crawl_policy_version'

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('crawl_source_profile.id'), nullable=False)
    generation = db.Column(db.Integer, nullable=False)
    document = db.Column(db.JSON, nullable=False)
    document_hash = db.Column(db.String(64), nullable=False)
    source_generation = db.Column(db.Integer, nullable=False)
    source_fingerprint = db.Column(db.String(64), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.Index('idx_policy_profile_id', 'profile_id', 'id'),
                      db.UniqueConstraint('profile_id', 'generation', name='uq_policy_profile_generation'))


class CrawlSchemaVersion(db.Model):
    __tablename__ = 'crawl_schema_version'

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('crawl_source_profile.id'), nullable=False)
    recipe = db.Column(db.JSON, nullable=False)
    recipe_hash = db.Column(db.String(64), nullable=False)
    base_generation = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='candidate')
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.Index('idx_schema_profile_id', 'profile_id', 'id'),)


class CrawlPreviewReport(db.Model):
    __tablename__ = 'crawl_preview_report'

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'), nullable=False)
    generation = db.Column(db.Integer, nullable=False)
    source_fingerprint = db.Column(db.String(64), nullable=False)
    recipe_hash = db.Column(db.String(64), nullable=False)
    engine_version = db.Column(db.String(40), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False)
    report = db.Column(db.JSON, nullable=False)

    __table_args__ = (db.Index('idx_preview_version_id', 'version_id', 'id'),)
