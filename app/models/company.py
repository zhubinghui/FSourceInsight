from datetime import datetime
from sqlalchemy import func, select
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
    ai_analysis = db.Column(db.JSON)  # Structured analysis {overview, founders, core_tech, ...}
    ai_analysis_at = db.Column(db.DateTime)
    ai_revision_history = db.Column(db.JSON)  # [{timestamp, source, trigger, changes: [{field, old, new}]}]
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

    # Cached article count — set by view queries via with_article_count().
    # Falls back to a DB count query if not preloaded.
    _article_count = None

    @property
    def article_count(self):
        if self._article_count is not None:
            return self._article_count
        return self.article_associations.count()

    @classmethod
    def grenoble_with_counts(cls):
        """Load all Grenoble companies with article counts in a single query."""
        from app.models.article import ArticleCompany
        count_subq = (
            select(func.count(ArticleCompany.id))
            .where(ArticleCompany.company_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )
        rows = (
            db.session.query(cls, count_subq.label('cnt'))
            .filter(cls.is_grenoble == True)
            .order_by(cls.name)
            .all()
        )
        companies = []
        for company, cnt in rows:
            company._article_count = cnt or 0
            companies.append(company)
        return companies

    @property
    def summary_zh(self):
        """Get Chinese overview from structured ai_analysis."""
        if self.ai_analysis and isinstance(self.ai_analysis, dict):
            return self.ai_analysis.get('overview', '') or self.description or ''
        return self.description or ''
