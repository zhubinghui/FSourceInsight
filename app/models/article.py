from datetime import datetime
from app.extensions import db


class Article(db.Model):
    __tablename__ = 'article'

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), nullable=False)
    external_id = db.Column(db.String(500))
    url = db.Column(db.String(1000), nullable=False)

    # Multilingual content
    title_fr = db.Column(db.String(500), nullable=False)
    title_zh = db.Column(db.String(500))
    title_en = db.Column(db.String(500))
    content_fr = db.Column(db.Text)
    content_zh = db.Column(db.Text)
    content_en = db.Column(db.Text)
    summary_fr = db.Column(db.Text)
    summary_zh = db.Column(db.Text)
    summary_en = db.Column(db.Text)

    author = db.Column(db.String(200))
    image_url = db.Column(db.String(1000))
    published_at = db.Column(db.DateTime)
    crawled_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # LLM processing state
    llm_processed = db.Column(db.Boolean, nullable=False, default=False)
    llm_processed_at = db.Column(db.DateTime)
    llm_provider = db.Column(db.String(100))
    llm_model = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    categories = db.relationship(
        'Category', secondary='article_category', backref=db.backref('articles', lazy='dynamic')
    )
    companies = db.relationship(
        'ArticleCompany', backref='article', lazy='dynamic', cascade='all, delete-orphan'
    )

    __table_args__ = (
        db.UniqueConstraint('source_id', 'external_id', name='uq_article_external'),
        db.Index('idx_published_at', 'published_at'),
        db.Index('idx_crawled_at', 'crawled_at'),
    )

    def __repr__(self):
        return f'<Article {self.title_fr[:50]}>'


class ArticleCategory(db.Model):
    __tablename__ = 'article_category'

    article_id = db.Column(
        db.Integer, db.ForeignKey('article.id', ondelete='CASCADE'), primary_key=True
    )
    category_id = db.Column(
        db.Integer, db.ForeignKey('category.id'), primary_key=True
    )
    confidence = db.Column(db.Float)


class ArticleCompany(db.Model):
    __tablename__ = 'article_company'

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer, db.ForeignKey('article.id', ondelete='CASCADE'), nullable=False
    )
    company_id = db.Column(
        db.Integer, db.ForeignKey('company.id'), nullable=False
    )
    sentiment = db.Column(
        db.Enum('positive', 'negative', 'neutral', name='sentiment_enum'),
        default='neutral'
    )
    sentiment_score = db.Column(db.Float)
    mention_count = db.Column(db.Integer, default=1)
    is_primary = db.Column(db.Boolean, default=False)
    extracted_by = db.Column(
        db.Enum('llm', 'manual', 'rule', name='extraction_method_enum'),
        default='llm'
    )

    company = db.relationship('Company', backref=db.backref('article_associations', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('article_id', 'company_id', name='uq_article_company'),
        db.Index('idx_company_sentiment', 'company_id', 'sentiment'),
    )

    def __repr__(self):
        return f'<ArticleCompany article={self.article_id} company={self.company_id}>'
