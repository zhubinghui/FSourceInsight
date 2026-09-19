"""Directory detail pages give discovery a verified address and organisation type."""
from app.crawlers import startup_discovery
from app.crawlers.directory_facts import fetch_directory_facts, parse_directory_facts
from app.models.company import Company
from app.models.startup_source import StartupSource


def _detail(org_type, address):
    return f'''<html><body><nav>Members</nav><h1>Member</h1>
    <h2>Practical Information</h2><p>Type of Organization</p><p>{org_type}</p><p>Year founded</p><p>2019</p>
    <p>Themes</p><p>Microelectronics</p><p>Markets</p><p>Industry</p><p>Minalogic member since 01/01/2020</p>
    <h2>Contact details</h2><p>Adress</p><p>{address}</p><p>Contact</p><p>Jane Example</p></body></html>'''


def test_parses_isere_sme_and_lyon_bank():
    assert parse_directory_facts(_detail('SME', '12 rue Exemple 38000 GRENOBLE')) == {
        'postcode': '38000', 'city': 'Grenoble', 'entity_type': 'company'}
    assert parse_directory_facts(_detail('Bank & Investor', 'CCI de Lyon 3 Place de la Bourse 69289 LYON CEDEX 02')) == {
        'postcode': '69289', 'city': 'Lyon', 'entity_type': 'ecosystem_support'}
    assert parse_directory_facts(_detail('Higher education & Research establishment', '38400 SAINT-MARTIN-D\'HÈRES'))[
        'entity_type'] == 'research_education'
    assert parse_directory_facts('<html><body>No address here</body></html>') == {}


def test_fetch_uses_the_safe_http_stack_and_fails_closed(fetch_network):
    fetch_network.configure(routes={'https://test.invalid/member-directory/acme/': {
        'body': _detail('Large corporation', '1 avenue Exemple 38920 CROLLES')}})

    assert fetch_directory_facts('https://test.invalid/member-directory/acme/') == {
        'postcode': '38920', 'city': 'Crolles', 'entity_type': 'corporate'}
    assert fetch_directory_facts('https://test.invalid/member-directory/missing/') == {}
    assert fetch_directory_facts('http://169.254.169.254/member-directory/x/') == {}


def test_discovery_only_maps_entries_with_an_isere_or_unknown_address(db, monkeypatch):
    listing = '''<a href="https://directory.test/member-directory/acme-chips/">Acme Chips</a>
                 <a href="https://directory.test/member-directory/lyon-bank/">Lyon Bank</a>
                 <a href="https://directory.test/member-directory/no-address/">No Address</a>'''

    class Response:
        status_code, text = 200, listing
        def raise_for_status(self): pass

    class Missing(Response):
        status_code, text = 404, ''

    monkeypatch.setattr(startup_discovery.requests, 'get',
                        lambda url, **kw: Response() if url.endswith('/member-directory/') else Missing())
    monkeypatch.setattr(startup_discovery, '_generate_analyses_for_new', lambda source: None)
    facts = {'acme-chips': {'postcode': '38000', 'city': 'Grenoble', 'entity_type': 'company'},
             'lyon-bank': {'postcode': '69002', 'city': 'Lyon', 'entity_type': 'ecosystem_support'}}
    monkeypatch.setattr(startup_discovery, 'fetch_directory_facts',
                        lambda url: facts.get(url.rstrip('/').rsplit('/', 1)[1], {}))
    db.session.add(StartupSource(name='directory', url='https://directory.test/member-directory/'))
    db.session.commit()

    startup_discovery.scan_startup_sources.run()

    found = {c.name: (c.is_grenoble, c.postcode, c.entity_type, c.review_status) for c in Company.query.all()}
    assert found == {'Acme Chips': (True, '38000', 'company', 'pending'),
                     'Lyon Bank': (False, '69002', 'ecosystem_support', 'pending'),
                     'No Address': (True, None, None, 'pending')}
