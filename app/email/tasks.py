import logging
from celery_app import celery
from app.models.user import User
from app.email.digest import build_daily_digest, find_keyword_matches
from app.email.sender import send_digest_email, send_keyword_alert

logger = logging.getLogger(__name__)


@celery.task(name='app.email.tasks.send_daily_digest', queue='email')
def send_daily_digest():
    """Send daily digest emails to all subscribed users."""
    users = User.query.filter_by(
        is_active_user=True,
        receive_daily_digest=True,
    ).all()

    sent = 0
    for user in users:
        try:
            digest = build_daily_digest(user)
            if digest:
                send_digest_email(user, digest)
                sent += 1
        except Exception as e:
            logger.error(f'Failed to send digest to {user.email}: {e}')

    # Also send keyword alerts
    all_users = User.query.filter_by(is_active_user=True).all()
    alerts = 0
    for user in all_users:
        try:
            matches = find_keyword_matches(user)
            if matches:
                send_keyword_alert(user, matches)
                alerts += 1
        except Exception as e:
            logger.error(f'Failed to send keyword alert to {user.email}: {e}')

    logger.info(f'Daily email job: {sent} digests, {alerts} keyword alerts sent')
    return {'digests_sent': sent, 'alerts_sent': alerts}
