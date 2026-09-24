"""Company page weekly sentiment chart: one bar per Monday-start week, in date order."""
import json
import re
from datetime import datetime

import pytest

from app.extensions import db
from app.models.article import Article, ArticleCompany
from app.models.company import Company
from app.models.source import NewsSource


@pytest.fixture
def mentions(app):
    from sqlalchemy import event

    @event.listens_for(db.engine, 'connect')
    def mysql_dialect_functions(connection, record):
        # Only lets the previous MySQL-only query run under SQLite for the red check.
        connection.create_function('yearweek', 1, lambda value: value and int(
            datetime.fromisoformat(value).strftime('%Y%U')))

    db.engine.dispose()
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
    company = Company(name='Trend Synthetic', slug='trend-synthetic')
    db.session.add_all([source, company])
    db.session.flush()

    def mention(day, sentiment):
        article = Article(source_id=source.id, url=f'https://test.invalid/{day}-{sentiment}',
                          title_fr=f'{day} {sentiment}', published_at=datetime.fromisoformat(day))
        db.session.add(article)
        db.session.flush()
        db.session.add(ArticleCompany(article_id=article.id, company_id=company.id, sentiment=sentiment))
    return mention


def trend(client):
    page = client.get('/companies/trend-synthetic')
    assert page.status_code == 200
    return json.loads(re.search(r'const trendData = (\{.*?\});', page.get_data(as_text=True)).group(1))


def test_one_week_is_one_bar_whatever_the_sentiment(client, mentions):
    mentions('2026-09-14T09:00:00', 'negative')  # Monday
    mentions('2026-09-15T09:00:00', 'positive')
    mentions('2026-09-20T22:00:00', 'positive')  # Sunday, same ISO week
    db.session.commit()
    assert trend(client) == {'labels': ['09/14'], 'positive': [2], 'neutral': [0], 'negative': [1]}


def test_weeks_across_new_year_stay_in_date_order(client, mentions):
    mentions('2025-12-29T09:00:00', 'neutral')
    mentions('2026-01-05T09:00:00', 'positive')
    db.session.commit()
    data = trend(client)
    assert data['labels'] == ['12/29', '01/05']
    assert data['neutral'] == [1, 0] and data['positive'] == [0, 1]
