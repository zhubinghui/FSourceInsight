from datetime import datetime
from app.extensions import db


class StartupSource(db.Model):
    """Configurable sources for discovering Grenoble ecosystem entities.

    Supports both startups (portfolio pages, directories) and research
    labs (institutional pages). Type field controls how discovered
    entities are tagged in the Company table.
    """
    __tablename__ = 'startup_source'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(500))
    source_type = db.Column(db.String(50), nullable=False, default='startup')  # startup, research_lab
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_scanned_at = db.Column(db.DateTime)
    companies_found = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<StartupSource {self.name}>'
