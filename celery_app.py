from celery import Celery
from celery.schedules import crontab

from app import create_app
from app.extensions import db


def make_celery(app=None):
    if app is None:
        app = create_app()

    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL'],
        backend=app.config['CELERY_RESULT_BACKEND'],
    )
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Europe/Paris',
        enable_utc=True,
        include=[
            'app.crawlers.tasks',
            'app.llm.tasks',
            'app.email.tasks',
        ],
        task_routes={
            'app.crawlers.tasks.*': {'queue': 'crawl'},
            'app.llm.tasks.*': {'queue': 'llm'},
            'app.email.tasks.*': {'queue': 'email'},
        },
        beat_schedule={
            'schedule-crawls': {
                'task': 'app.crawlers.tasks.schedule_all_crawls',
                'schedule': 60.0,  # Check every minute which sources need crawling
            },
            'daily-digest': {
                'task': 'app.email.tasks.send_daily_digest',
                'schedule': crontab(hour=7, minute=0),  # 7:00 AM Paris time
            },
            'crawl-health-check': {
                'task': 'app.crawlers.tasks.check_crawl_health',
                'schedule': crontab(hour='*/6', minute=0),  # Every 6 hours
            },
        },
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


celery = make_celery()
