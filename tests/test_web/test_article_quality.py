import pytest

from app.models.article import Article
from app.models.source import NewsSource


@pytest.mark.parametrize('level,language', [('metadata_only', 'en'), ('excerpt', 'unknown'), (None, None)])
def test_http_exposes_quality_and_language_without_private_provenance(client, db, level, language):
    source = NewsSource(name='Synthetic', slug='quality-http', url='https://news.test.invalid', category='regional')
    db.session.add(source)
    db.session.flush()
    article = Article(source_id=source.id, external_id='synthetic', url='https://news.test.invalid/research',
                      title_fr='Source title', content_level=level, source_language=language,
                      crawl_provenance={'private': 'not-public-evidence'})
    db.session.add(article)
    db.session.commit()
    data = client.get(f'/api/v1/news/{article.id}').get_json()
    assert data['content_level'] == (level or 'unknown')
    assert data['source_language'] == (language or 'unknown')
    assert 'crawl_provenance' not in data
    response = client.get(f'/news/{article.id}')
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert f'data-content-level="{level or "unknown"}"' in text
    assert f'Original ({language or "unknown"})' in text
    assert 'not-public-evidence' not in text
