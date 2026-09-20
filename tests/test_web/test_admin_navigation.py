"""The admin sidebar groups pages by job and marks exactly one current page."""
import pytest
from bs4 import BeautifulSoup

from app.models.company import Company
from app.models.source import NewsSource


def _sidebar(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    nav = BeautifulSoup(response.text, 'html.parser').select_one('aside')
    sections = {}
    for heading in nav.select('.sidebar-section'):
        links = heading.find_next_sibling('ul').select('a')
        sections[heading.get_text(strip=True)] = [' '.join(a.get_text(' ', strip=True).split()) for a in links]
    active = [' '.join(a.get_text(' ', strip=True).split()) for a in nav.select('.sidebar-nav a.active')]
    return sections, active


def test_sidebar_is_grouped_by_job_with_a_review_queue(db, client, login):
    db.session.add_all([Company(name='Pending One', slug='pending-one', review_status='pending'),
                        Company(name='Pending Two', slug='pending-two', review_status='pending')])
    db.session.commit()
    login('admin')

    sections, active = _sidebar(client, '/admin/')

    assert sections == {
        'Monitoring': ['Dashboard', 'Crawl Logs', 'Email Logs'],
        'Sources': ['News Sources', 'Discovery Sources'],
        'Ecosystem': ['Companies', 'Review Queue 2', 'Sector Groups'],
        'AI / LLM': ['Task Routing', 'Model Config', 'Usage & Cost'],
        'System': ['Users', 'Settings'],
    }
    assert active == ['Dashboard']


@pytest.mark.parametrize('path, expected', [
    ('/admin/companies', 'Companies'),
    ('/admin/companies/merge', 'Companies'),
    ('/admin/companies/duplicates', 'Companies'),
    ('/admin/companies?review=pending', 'Review Queue 0'),
    ('/admin/startup-sources', 'Discovery Sources'),
    ('/admin/sources', 'News Sources'),
    ('/admin/sources/{source}/crawl-config', 'News Sources'),
    ('/admin/sources/{source}/crawl-config/policies', 'News Sources'),
    ('/admin/users', 'Users'),
    ('/admin/llm-config', 'Model Config'),
])
def test_exactly_one_sidebar_entry_is_current(db, client, login, path, expected):
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://news.test.invalid/',
                        feed_type='rss', category='national')
    db.session.add(source)
    db.session.commit()
    login('admin')

    _, active = _sidebar(client, path.format(source=source.id))

    assert active == [expected]


def test_lab_sources_are_shown_as_not_scanned(db, client, login):
    from app.models.startup_source import StartupSource
    db.session.add(StartupSource(name='Synthetic Lab', url='https://lab.test/', source_type='research_lab'))
    db.session.commit()
    login('admin')

    listing = BeautifulSoup(client.get('/admin/startup-sources').text, 'html.parser')
    row = next(tr for tr in listing.select('tbody tr') if 'Synthetic Lab' in tr.get_text())
    assert 'not scanned' in row.get_text(' ', strip=True).lower()

    form = BeautifulSoup(client.get('/admin/startup-sources/new').text, 'html.parser')
    assert 'not scanned' in form.select_one('option[value=research_lab]').get_text().lower()
