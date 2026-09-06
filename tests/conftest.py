"""Offline test environment; never reads .env or connects to live services."""
import os
import socket

# Celery's app is created on import. Keep collection and execution on test config.
os.environ['FLASK_ENV'] = 'testing'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['CELERY_BROKER_URL'] = 'memory://'
os.environ['SENTRY_DSN'] = ''
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'

import pytest
from bs4 import BeautifulSoup
from flask import g
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Tests must mock external network/SMTP/LLM calls')

    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Separate connections are needed to test independent usage transactions.
    # A fresh file per test also isolates code that commits its own transaction.
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "test.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'app.log'))
    application = create_app('testing')
    application.config.update(SECRET_KEY='test-only-secret', WTF_CSRF_ENABLED=True)

    @application.teardown_request
    def clear_request_user(error):
        # The outer test app context is for DB assertions; real requests have
        # separate g objects. Clear per-request user and CSRF caches as in production.
        for key in list(g):
            g.pop(key, None)

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()
        _db.engine.dispose()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users(db):
    accounts = {}
    for name, admin in [('owner', False), ('other', False), ('admin', True)]:
        user = User(email=f'{name}@test.invalid', name=name, is_admin=admin,
                    password_hash=generate_password_hash('original-password'))
        db.session.add(user)
        accounts[name] = user
    db.session.commit()
    return accounts


@pytest.fixture
def csrf_token(client):
    def token(path='/auth/login'):
        response = client.get(path)
        assert response.status_code == 200
        return BeautifulSoup(response.text, 'html.parser').select_one('input[name=csrf_token]')['value']
    return token


@pytest.fixture
def login(client, csrf_token, users):
    def sign_in(name='owner', password='original-password', next_url=''):
        return client.post('/auth/login', query_string={'next': next_url}, data={
            'email': users[name].email, 'password': password, 'csrf_token': csrf_token(),
        })
    return sign_in
