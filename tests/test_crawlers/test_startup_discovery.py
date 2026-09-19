"""Discovery must not turn arbitrary page text into ecosystem companies."""
import pytest

from app.crawlers import startup_discovery
from app.models.company import Company
from app.models.startup_source import StartupSource


class _Response:
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.fixture
def pages(monkeypatch):
    """Serve synthetic pages to the legacy requests path and record fetched URLs."""
    served, fetched = {}, []

    def get(url, **kwargs):
        fetched.append(url)
        if url not in served:
            response = _Response('')
            response.status_code = 404
            return response
        return _Response(served[url])

    monkeypatch.setattr(startup_discovery.requests, 'get', get)
    monkeypatch.setattr(startup_discovery, '_generate_analyses_for_new', lambda source: None)
    # Detail-page facts have their own tests through the safe HTTP stack.
    monkeypatch.setattr(startup_discovery, 'fetch_directory_facts', lambda url: {})
    return served, fetched


def _source(db, url, source_type='startup'):
    source = StartupSource(name='synthetic', url=url, source_type=source_type)
    db.session.add(source)
    db.session.commit()
    return source


def _names():
    return {c.name for c in Company.query.all()}


LAB_HOME = '''<html><body>
<p>From Tuesday April 07: seminar on spin ice in room D420</p>
<p>Newsletter: subscribe to receive our latest publications</p>
<p>Akila Example, PhD student joining the modelling team</p>
</body></html>'''

DIRECTORY = '''<html><body>
<a href="https://directory.test/member-directory/acme-chips/">Acme Chips</a>
<a href="https://directory.test/member-directory/beta-sensors/">Beta Sensors</a>
<p>With mailing tool: we use a provider to send our newsletter to members</p>
</body></html>'''

TEXT_ONLY_PORTFOLIO = '''<html><body>
<p>Gamma Photonics: integrated lasers on silicon for datacom links</p>
</body></html>'''


def test_research_lab_source_creates_no_companies(db, pages):
    served, fetched = pages
    served['https://lab.test/'] = LAB_HOME
    _source(db, 'https://lab.test/', source_type='research_lab')

    startup_discovery.scan_startup_sources.run()

    assert _names() == set()
    assert fetched == []


def test_directory_page_ignores_free_text_fragments(db, pages):
    served, _ = pages
    served['https://directory.test/member-directory/'] = DIRECTORY
    _source(db, 'https://directory.test/member-directory/')

    startup_discovery.scan_startup_sources.run()

    assert _names() == {'Acme Chips', 'Beta Sensors'}


def test_text_only_portfolio_still_discovers_companies(db, pages):
    served, _ = pages
    served['https://portfolio.test/startups'] = TEXT_ONLY_PORTFOLIO
    _source(db, 'https://portfolio.test/startups')

    startup_discovery.scan_startup_sources.run()

    assert _names() == {'Gamma Photonics'}


def test_discovered_companies_wait_for_review(db, pages):
    served, _ = pages
    served['https://directory.test/member-directory/'] = DIRECTORY
    _source(db, 'https://directory.test/member-directory/')

    startup_discovery.scan_startup_sources.run()

    assert {c.review_status for c in Company.query.all()} == {'pending'}


def test_rejected_entry_is_not_rediscovered(db, pages):
    served, _ = pages
    served['https://directory.test/member-directory/'] = DIRECTORY
    _source(db, 'https://directory.test/member-directory/')
    db.session.add(Company(name='Acme Chips', slug='acme-chips', is_grenoble=False, review_status='rejected'))
    db.session.commit()

    startup_discovery.scan_startup_sources.run()

    rejected = Company.query.filter_by(slug='acme-chips').one()
    assert (rejected.review_status, rejected.is_grenoble) == ('rejected', False)
    assert Company.query.filter_by(name='Acme Chips').count() == 1
