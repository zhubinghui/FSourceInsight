from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import redis

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()
csrf = CSRFProtect()

# Redis client (initialized in app factory)
redis_client = None


def init_redis(app):
    global redis_client
    redis_client = redis.from_url(app.config['REDIS_URL'])
    return redis_client
