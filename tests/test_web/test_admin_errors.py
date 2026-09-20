"""Refused admin requests keep the admin layout, say why, and offer a way back."""
from bs4 import BeautifulSoup

from app.models.company import Company
from app.models.source import NewsSource


def test_refused_admin_request_renders_inside_the_admin_layout(db, client, login):
    company = Company(name='Pending Sensors', slug='pending-sensors', review_status='pending')
    db.session.add(company)
    db.session.commit()
    login('admin')
    token = BeautifulSoup(client.get('/admin/companies').text, 'html.parser').select_one(
        'input[name=csrf_token]')['value']

    response = client.post(f'/admin/companies/{company.id}/review',
                           data={'csrf_token': token, 'status': 'published'},
                           headers={'Referer': 'http://localhost/admin/companies?review=pending'})

    assert response.status_code == 400
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('aside .sidebar-nav') is not None
    assert 'could not be processed' in page.get_text(' ', strip=True)
    assert page.select_one('a.error-back')['href'] == '/admin/companies?review=pending'


def test_error_back_link_never_leaves_the_site(db, client, login):
    login('admin')

    response = client.get('/admin/companies/999999/edit', headers={'Referer': 'https://evil.example/x'})

    assert response.status_code == 404
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('aside .sidebar-nav') is not None
    assert page.select_one('a.error-back')['href'] == '/admin/'


def test_nested_crawl_config_refusals_use_the_same_page(db, client, login):
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://news.test.invalid/',
                        feed_type='rss', category='national')
    db.session.add(source)
    db.session.commit()
    login('admin')
    path = f'/admin/sources/{source.id}/crawl-config'
    token = BeautifulSoup(client.get(path).text, 'html.parser').select_one('input[name=csrf_token]')['value']

    response = client.post(path, data={'csrf_token': token, 'recipe': 'not json'})

    assert response.status_code == 400
    assert BeautifulSoup(response.text, 'html.parser').select_one('aside .sidebar-nav') is not None


def test_anonymous_refusals_do_not_reveal_the_admin_layout(db, client):
    response = client.post('/admin/companies/1/review', data={'status': 'approved'})

    assert response.status_code in (302, 400)
    assert 'sidebar-nav' not in response.text and 'Review Queue' not in response.text
