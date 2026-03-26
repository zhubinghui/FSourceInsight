"""Structured logging configuration for Flask and Celery."""
import logging
import logging.config
import os


def setup_logging(app=None):
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_format = os.environ.get('LOG_FORMAT', 'text')  # 'text' or 'json'

    if log_format == 'json':
        formatter = {
            'format': '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
        }
    else:
        formatter = {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        }

    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': formatter,
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
                'stream': 'ext://sys.stdout',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'default',
                'filename': os.environ.get('LOG_FILE', '/tmp/fsourceinsight.log'),
                'maxBytes': 10 * 1024 * 1024,  # 10MB
                'backupCount': 5,
            },
        },
        'root': {
            'level': log_level,
            'handlers': ['console', 'file'],
        },
        'loggers': {
            'app': {'level': log_level},
            'celery': {'level': log_level},
            'app.crawlers': {'level': log_level},
            'app.llm': {'level': log_level},
            # Quiet noisy libraries
            'urllib3': {'level': 'WARNING'},
            'feedparser': {'level': 'WARNING'},
            'litellm': {'level': 'WARNING'},
        },
    }

    logging.config.dictConfig(config)

    if app:
        app.logger.setLevel(log_level)


def init_sentry(app):
    """Initialize Sentry error tracking if DSN is configured."""
    dsn = os.environ.get('SENTRY_DSN')
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                FlaskIntegration(),
                CeleryIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_RATE', '0.1')),
            environment=os.environ.get('FLASK_ENV', 'production'),
            release=os.environ.get('APP_VERSION', 'unknown'),
        )
        app.logger.info('Sentry initialized')
    except ImportError:
        app.logger.debug('sentry-sdk not installed, skipping')
