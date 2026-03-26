from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(300), nullable=False, unique=True)
    name = db.Column(db.String(200))
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    receive_daily_digest = db.Column(db.Boolean, default=True)
    preferred_language = db.Column(
        db.Enum('fr', 'zh', 'en', name='language_enum'), default='zh'
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    subscriptions = db.relationship(
        'KeywordSubscription', backref='user', lazy='dynamic', cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<User {self.email}>'

    @property
    def is_active(self):
        return self.is_active_user


class KeywordSubscription(db.Model):
    __tablename__ = 'keyword_subscription'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False
    )
    keyword = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'keyword', name='uq_user_keyword'),
    )

    def __repr__(self):
        return f'<KeywordSubscription user={self.user_id} keyword={self.keyword}>'
