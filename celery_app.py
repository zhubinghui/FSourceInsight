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
            'app.crawlers.startup_discovery',
            'app.crawlers.learning_tasks',
            'app.llm.tasks',
            'app.llm.startup_tasks',
            'app.llm.refresh_tasks',
            'app.llm.article_tasks',
            'app.email.tasks',
        ],
        task_routes={
            'app.crawlers.tasks.*': {'queue': 'crawl'},
            'app.crawlers.learning_tasks.*': {'queue': 'crawl_learn'},
            'app.llm.tasks.*': {'queue': 'llm'},
            'app.llm.startup_tasks.*': {'queue': 'llm'},
            'app.llm.refresh_tasks.*': {'queue': 'llm'},
            'app.llm.article_tasks.*': {'queue': 'llm'},
            'app.email.tasks.*': {'queue': 'email'},
        },
        beat_schedule={
            'dispatch-due-crawls': {
                'task': 'app.crawlers.tasks.dispatch_due_crawls',
                'schedule': 60.0,  # One next-due rule: frequency plus the daily anchor (spec §5.4)
            },
            'daily-digest': {
                'task': 'app.email.tasks.send_daily_digest',
                'schedule': crontab(hour=7, minute=0),  # 7:00 AM Paris time
            },
            'crawl-health-check': {
                'task': 'app.crawlers.tasks.check_crawl_health',
                'schedule': crontab(hour='*/6', minute=0),  # Every 6 hours
            },
            'recover-startup-analysis': {
                'task': 'app.llm.startup_tasks.recover',
                'schedule': 60.0,
            },
            'recover-company-refresh': {
                'task': 'app.llm.refresh_tasks.recover',
                'schedule': 60.0,
            },
            'recover-article-llm': {
                'task': 'app.llm.article_tasks.recover',
                'schedule': 60.0,
            },
            'startup-discovery': {
                'task': 'app.crawlers.startup_discovery.scan_startup_sources',
                'schedule': crontab(hour=2, minute=30),  # Daily at 2:30 AM
            },
        },
    )

    if app.config.get('CRAWL_LEARNING_ENABLED') is True:
        celery.conf.beat_schedule['recover-crawl-learning'] = {
            'task': 'app.crawlers.learning_tasks.recover', 'schedule': 30.0,
        }

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


celery = make_celery()
