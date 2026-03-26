from datetime import datetime
from app.extensions import db


class NewsSource(db.Model):
    __tablename__ = 'news_source'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), nullable=False, unique=True)
    url = db.Column(db.String(500), nullable=False)
    feed_url = db.Column(db.String(500))
    feed_type = db.Column(
        db.Enum('rss', 'atom', 'html_scrape', name='feed_type_enum'),
        nullable=False, default='rss'
    )
    crawler_class = db.Column(db.String(200))
    category = db.Column(
        db.Enum('national', 'regional', 'institutional', name='source_category_enum'),
        nullable=False
    )
    crawl_frequency_minutes = db.Column(db.Integer, nullable=False, default=60)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_crawled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    articles = db.relationship('Article', backref='source', lazy='dynamic')
    crawl_logs = db.relationship('CrawlLog', backref='source', lazy='dynamic')

    def __repr__(self):
        return f'<NewsSource {self.name}>'

    @property
    def is_due_for_crawl(self):
        if not self.last_crawled_at:
            return True
        from datetime import timedelta
        elapsed = datetime.utcnow() - self.last_crawled_at
        return elapsed >= timedelta(minutes=self.crawl_frequency_minutes)


class CrawlLog(db.Model):
    __tablename__ = 'crawl_log'

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    status = db.Column(
        db.Enum('running', 'success', 'failed', name='crawl_status_enum'),
        default='running'
    )
    articles_found = db.Column(db.Integer, default=0)
    articles_new = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_source_started', 'source_id', 'started_at'),
    )

    def __repr__(self):
        return f'<CrawlLog source={self.source_id} status={self.status}>'
