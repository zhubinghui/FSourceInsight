"""The public ecosystem map only shows reviewed entities."""
from bs4 import BeautifulSoup

from app.models.company import Company


def _company(db, name, **fields):
    company = Company(name=name, slug=name.lower().replace(' ', '-'), is_grenoble=True, **fields)
    db.session.add(company)
    db.session.commit()
    return company


def _page_text(client, **query):
    response = client.get('/companies/', query_string=query)
    assert response.status_code == 200
    return BeautifulSoup(response.text, 'html.parser').get_text(' ', strip=True)


def test_map_shows_approved_and_hides_pending_and_rejected(db, client):
    _company(db, 'Approved Chips')
    _company(db, 'Pending Sensors', review_status='pending')
    _company(db, 'From Tuesday April 07', review_status='rejected')

    text = _page_text(client)

    assert 'Approved Chips' in text
    assert 'Pending Sensors' not in text
    assert 'From Tuesday April 07' not in text


def test_company_list_hides_rejected_entries(db, client):
    _company(db, 'Approved Chips')
    _company(db, 'From Tuesday April 07', review_status='rejected')

    text = _page_text(client, view='list')

    assert 'Approved Chips' in text
    assert 'From Tuesday April 07' not in text


def test_live_search_hides_rejected_entries(db, client):
    _company(db, 'Approved Chips')
    _company(db, 'From Tuesday April 07', review_status='rejected')

    response = client.get('/companies/search', query_string={'q': 'a'})

    assert 'Approved Chips' in response.text
    assert 'From Tuesday April 07' not in response.text


def _groups(client):
    """Map heading -> (entry names, expanded?) in page order."""
    soup = BeautifulSoup(client.get('/companies/').text, 'html.parser')
    groups = {}
    for section in soup.select('details.ecosystem-group'):
        names = [node.get_text(strip=True) for node in section.select('.fw-semibold')]
        groups[section.select_one('h5').get_text(strip=True)] = (names, section.has_attr('open'))
    return groups


def test_institutions_are_grouped_by_entity_type_not_sector(db, client):
    from app.models.sector_group import SectorGroup
    db.session.add(SectorGroup(name='Semiconductor', icon='cpu', color='#2563EB',
                               keywords=['semiconductor'], sort_order=1))
    _company(db, 'Acme Chips', sector='Semiconductor', entity_type='company')
    _company(db, 'CEA Example Lab', sector='Semiconductor', entity_type='research_education')
    _company(db, 'Example Bank', sector='Semiconductor', entity_type='ecosystem_support')
    _company(db, 'Legacy Untyped', sector='Semiconductor')

    groups = _groups(client)

    assert list(groups) == ['Semiconductor', 'Schools & Research', 'Ecosystem support']
    assert groups['Semiconductor'] == (['Acme Chips', 'Legacy Untyped'], True)
    assert groups['Schools & Research'] == (['CEA Example Lab'], True)
    assert groups['Ecosystem support'] == (['Example Bank'], False)


def test_multi_topic_sector_is_grouped_by_its_first_topic(db, client):
    from app.models.sector_group import SectorGroup
    db.session.add_all([
        SectorGroup(name='AI & Computing', icon='cpu', color='#111111', keywords=['ai', 'quantum'], sort_order=1),
        SectorGroup(name='MedTech & Health', icon='heart', color='#222222', keywords=['medtech', 'health'], sort_order=2),
        SectorGroup(name='Energy & CleanTech', icon='sun', color='#333333', keywords=['energy'], sort_order=3),
    ])
    _company(db, 'Glucose Loop', sector='MedTech / AI')
    _company(db, 'Quantum Dots', sector='Quantum Computing')
    _company(db, 'Hydro Maintenance', sector='Maintenance / Energy')

    groups = _groups(client)

    assert groups['MedTech & Health'][0] == ['Glucose Loop']
    assert groups['AI & Computing'][0] == ['Quantum Dots']
    # "ai" inside "maintenance" is not a topic.
    assert groups['Energy & CleanTech'][0] == ['Hydro Maintenance']
