from datetime import datetime
from app.extensions import db


class StartupSource(db.Model):
    """Configurable sources for discovering new Grenoble startups.

    Each entry is a URL (portfolio page, member directory, etc.)
    that is periodically scraped to find new company names.
    """
    __tablename__ = 'startup_source'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_scanned_at = db.Column(db.DateTime)
    companies_found = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<StartupSource {self.name}>'
