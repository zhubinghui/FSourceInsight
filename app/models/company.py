from datetime import datetime
from app.extensions import db


class Company(db.Model):
    __tablename__ = 'company'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(300), nullable=False)
    slug = db.Column(db.String(300), nullable=False, unique=True)
    aliases = db.Column(db.JSON)  # ["STMicro", "ST Microelectronics", ...]
    description = db.Column(db.Text)
    website = db.Column(db.String(500))
    logo_url = db.Column(db.String(500))
    headquarters = db.Column(db.String(200))
    is_grenoble = db.Column(db.Boolean, nullable=False, default=False)
    sector = db.Column(db.String(200))
    company_stage = db.Column(db.String(50))  # startup, scale-up, mature, research_institute
    spinoff_origin = db.Column(db.String(200))  # e.g. "CEA-Leti", "Inria", "UGA"
    ai_analysis = db.Column(db.Text)  # LLM-generated company analysis (JSON or Markdown)
    ai_analysis_at = db.Column(db.DateTime)
    is_auto_created = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f'<Company {self.name}>'

    @property
    def all_names(self):
        names = [self.name]
        if self.aliases:
            names.extend(self.aliases)
        return names

    @property
    def article_count(self):
        return self.article_associations.count()
