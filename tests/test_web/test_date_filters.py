"""date_to names a whole day: articles from that day are included, the next day's are not."""
from datetime import datetime

import pytest

from app.extensions import db
from app.models.article import Article
from app.models.source import NewsSource


@pytest.fixture
def articles(app):
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
    db.session.add(source)
    db.session.flush()
    for title, published in [('Day before', datetime(2026, 9, 19, 23, 59, 59)),
                              ('Morning', datetime(2026, 9, 20, 0, 0, 0)),
                              ('Noon', datetime(2026, 9, 20, 12, 0, 0)),
                              ('Late', datetime(2026, 9, 20, 23, 59, 59)),
                              ('Next day', datetime(2026, 9, 21, 0, 0, 0))]:
        db.session.add(Article(source_id=source.id, url=f'https://test.invalid/{title}',
                               title_fr=title, published_at=published))
    db.session.commit()


def test_api_date_range_covers_whole_days(client, articles):
    response = client.get('/api/v1/news', query_string={'date_from': '2026-09-20', 'date_to': '2026-09-20'})
    assert response.status_code == 200
    assert sorted(a['title_fr'] for a in response.get_json()['articles']) == ['Late', 'Morning', 'Noon']


def test_news_page_date_range_covers_whole_days(client, articles):
    response = client.get('/', query_string={'date_from': '2026-09-20', 'date_to': '2026-09-20'})
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert all(title in body for title in ('Morning', 'Noon', 'Late'))
    assert 'Day before' not in body and 'Next day' not in body
