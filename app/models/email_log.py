from datetime import datetime
from app.extensions import db


class EmailLog(db.Model):
    __tablename__ = 'email_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    email_type = db.Column(
        db.Enum('daily_digest', 'keyword_alert', name='email_type_enum'),
        nullable=False
    )
    subject = db.Column(db.String(500))
    article_count = db.Column(db.Integer)
    sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(
        db.Enum('sent', 'failed', name='email_status_enum'),
        default='sent'
    )
    error_message = db.Column(db.Text)

    user = db.relationship('User', backref=db.backref('email_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<EmailLog {self.email_type} user={self.user_id}>'
