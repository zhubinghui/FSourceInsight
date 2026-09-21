"""Administrators can find an article, see why it stalled, and requeue just that one."""
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from app.models.article import Article
from app.models.source import NewsSource


def _seed(db):
    now = datetime.utcnow()
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://news.test.invalid/',
                        feed_type='rss', category='national')
    other = NewsSource(name='Other Feed', slug='other', url='https://other.test.invalid/',
                       feed_type='rss', category='regional')
    db.session.add_all([source, other])
    db.session.flush()
    articles = [
        Article(source_id=source.id, url='https://news.test.invalid/1', title_fr='Soitec investit à Bernin',
                crawled_at=now, llm_processed=True, llm_processed_at=now, highlights=['investment']),
        Article(source_id=source.id, url='https://news.test.invalid/2', title_fr='Article en attente',
                crawled_at=now - timedelta(hours=2), llm_processed=False),
        Article(source_id=other.id, url='https://other.test.invalid/3', title_fr='Autre source',
                crawled_at=now - timedelta(days=1), llm_processed=True, llm_processed_at=now),
    ]
    db.session.add_all(articles)
    db.session.commit()
    return {article.title_fr: article.id for article in articles}, source.id


def _list(client, **query):
    response = client.get('/admin/articles', query_string=query)
    assert response.status_code == 200
    return BeautifulSoup(response.text, 'html.parser')


def _titles(page):
    return [cell.get_text(strip=True) for cell in page.select('tbody tr td:first-child a')]


def test_articles_can_be_filtered_by_state_source_and_text(db, client, login):
    _seed(db)
    login('admin')

    assert _titles(_list(client)) == ['Soitec investit à Bernin', 'Article en attente', 'Autre source']
    assert _titles(_list(client, state='unprocessed')) == ['Article en attente']
    assert _titles(_list(client, q='soitec')) == ['Soitec investit à Bernin']
    assert 'Pending (1)' in _list(client).get_text(' ', strip=True)


def test_filters_survive_pagination_and_a_source_filter(db, client, login):
    _, source_id = _seed(db)
    login('admin')

    page = _list(client, source=source_id, state='unprocessed')

    assert _titles(page) == ['Article en attente']
    assert [option['value'] for option in page.select('select[name=source] option')][0] == ''


def test_requeue_one_article_and_refuse_unknown_ones(db, client, login, monkeypatch):
    queued = []
    from app.llm import tasks
    monkeypatch.setattr(tasks.process_article_llm, 'delay', lambda article_id, **kw: queued.append((article_id, kw)))
    ids, _ = _seed(db)
    login('admin')
    page = _list(client, state='unprocessed')
    form = page.select_one('form[action$="/reprocess"]')
    data = {field['name']: field['value'] for field in form.select('input[name]')}

    response = client.post(form['action'], data=data)

    assert response.status_code == 302
    assert queued == [(ids['Article en attente'], {'force': True})]
    assert client.post('/admin/articles/999999/reprocess', data=data).status_code == 404


def test_article_detail_shows_pipeline_state_and_links_back(db, client, login):
    from app.models.article import ArticleCompany
    from app.models.company import Company
    ids, _ = _seed(db)
    company = Company(name='Soitec', slug='soitec')
    db.session.add(company)
    db.session.flush()
    db.session.add(ArticleCompany(article_id=ids['Soitec investit à Bernin'], company_id=company.id))
    db.session.commit()
    login('admin')

    page = BeautifulSoup(client.get(f"/admin/articles/{ids['Soitec investit à Bernin']}").text, 'html.parser')
    text = page.get_text(' ', strip=True)

    assert 'Soitec investit à Bernin' in text
    assert 'investment' in text
    assert page.select_one('a[href="https://news.test.invalid/1"]') is not None
    assert page.select_one(f'a[href="/admin/companies/{company.id}/edit"]').get_text(strip=True) == 'Soitec'
    assert [a.get_text(' ', strip=True) for a in page.select('aside .sidebar-nav a.active')] == ['Articles']


def test_articles_require_an_administrator(db, client, login):
    login('owner')
    assert client.get('/admin/articles').status_code == 302
