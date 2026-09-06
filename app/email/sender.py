import logging
from flask import render_template
from flask_mail import Message

from app.extensions import mail, db
from app.models.email_log import EmailLog

logger = logging.getLogger(__name__)


def send_digest_email(user, digest_data: dict):
    """Send daily digest email to a user."""
    subject = f"[FSourceInsight] Daily Tech News Digest - {digest_data['date']}"

    html = render_template(
        'daily_digest.html',
        articles=digest_data['articles'],
        top_insights=digest_data.get('top_insights', []),
        date=digest_data['date'],
        user=user,
    )

    msg = Message(subject=subject, recipients=[user.email], html=html)
    try:
        mail.send(msg)
        log = EmailLog(
            user_id=user.id,
            email_type='daily_digest',
            subject=subject,
            article_count=digest_data['article_count'],
            status='sent',
        )
        db.session.add(log)
        db.session.commit()
        logger.info(f'Sent daily digest to {user.email}')
    except Exception as e:
        log = EmailLog(
            user_id=user.id,
            email_type='daily_digest',
            subject=subject,
            status='failed',
            error_message=str(e),
        )
        db.session.add(log)
        db.session.commit()
        logger.error(f'Failed to send digest to {user.email}: {e}')
        raise


def send_keyword_alert(user, matches: list[dict]):
    """Send keyword alert email to a user."""
    subject = f"[FSourceInsight] Keyword Alert - {len(matches)} new articles"

    html = render_template(
        'keyword_alert.html',
        matches=matches,
        user=user,
    )

    msg = Message(subject=subject, recipients=[user.email], html=html)
    try:
        mail.send(msg)
        log = EmailLog(
            user_id=user.id,
            email_type='keyword_alert',
            subject=subject,
            article_count=len(matches),
            status='sent',
        )
        db.session.add(log)
        db.session.commit()
        logger.info(f'Sent keyword alert to {user.email}')
    except Exception as e:
        log = EmailLog(
            user_id=user.id,
            email_type='keyword_alert',
            subject=subject,
            status='failed',
            error_message=str(e),
        )
        db.session.add(log)
        db.session.commit()
        logger.error(f'Failed to send keyword alert to {user.email}: {e}')
        raise
