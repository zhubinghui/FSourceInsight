"""An administrator reviews discovered entities from the normal company form."""
from bs4 import BeautifulSoup

from app.models.company import Company


def _pending(db):
    company = Company(name='Pending Sensors', slug='pending-sensors', is_grenoble=True,
                      is_auto_created=True, review_status='pending')
    db.session.add(company)
    db.session.commit()
    return company.id


def _submit(client, company_id, **changes):
    path = f'/admin/companies/{company_id}/edit'
    form = BeautifulSoup(client.get(path).text, 'html.parser')
    data = {'csrf_token': form.select_one('input[name=csrf_token]')['value'],
            'name': 'Pending Sensors', 'is_grenoble': 'on', **changes}
    return client.post(path, data=data)


def test_admin_approves_pending_company_onto_the_map(db, client, login):
    company_id = _pending(db)
    login('admin')
    assert 'Pending Sensors' not in client.get('/companies/').text

    form = BeautifulSoup(client.get(f'/admin/companies/{company_id}/edit').text, 'html.parser')
    selected = form.select_one('select[name=review_status] option[selected]')
    assert selected['value'] == 'pending'

    assert _submit(client, company_id, review_status='approved').status_code == 302
    assert 'Pending Sensors' in client.get('/companies/').text


def test_unknown_or_missing_review_status_changes_nothing(db, client, login):
    company_id = _pending(db)
    login('admin')

    _submit(client, company_id, review_status='published')
    _submit(client, company_id)

    assert db.session.get(Company, company_id).review_status == 'pending'


def test_admin_sets_entity_type_and_unknown_type_is_ignored(db, client, login):
    company_id = _pending(db)
    login('admin')

    _submit(client, company_id, entity_type='research_education')
    assert db.session.get(Company, company_id).entity_type == 'research_education'
    form = BeautifulSoup(client.get(f'/admin/companies/{company_id}/edit').text, 'html.parser')
    assert form.select_one('select[name=entity_type] option[selected]')['value'] == 'research_education'

    _submit(client, company_id, entity_type='charity')
    assert db.session.get(Company, company_id).entity_type == 'research_education'
