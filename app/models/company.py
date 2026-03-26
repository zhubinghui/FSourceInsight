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
