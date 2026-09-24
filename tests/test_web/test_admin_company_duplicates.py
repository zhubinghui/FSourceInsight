"""Likely duplicates are suggested so an administrator can merge them in one step."""
from bs4 import BeautifulSoup

from app.models.company import Company


def _add(db, name, slug, **fields):
    company = Company(name=name, slug=slug, **fields)
    db.session.add(company)
    db.session.commit()
    return company.id


def test_suggests_spacing_suffix_and_word_order_variants_and_merges(db, client, login):
    keep = _add(db, 'Microlight 3D', 'microlight-3d')
    _add(db, 'MICROLIGHT3D', 'microlight3d', is_auto_created=True)
    _add(db, 'Orioma', 'orioma')
    _add(db, 'ORIOMA SAS', 'orioma-sas', is_auto_created=True)
    _add(db, 'Lancey Energy Storage', 'lancey-energy-storage')
    _add(db, 'Lancey Storage Energy', 'lancey-storage-energy', is_auto_created=True)
    _add(db, 'Soitec', 'soitec')
    _add(db, 'Soitec Junk', 'soitec-sa', review_status='rejected')
    login('admin')

    page = BeautifulSoup(client.get('/admin/companies/duplicates').text, 'html.parser')
    groups = [[cell.get_text(strip=True) for cell in group.select('.duplicate-name')]
              for group in page.select('.duplicate-group')]

    assert groups == [['Lancey Energy Storage', 'Lancey Storage Energy'],
                      ['Microlight 3D', 'MICROLIGHT3D'],
                      ['Orioma', 'ORIOMA SAS']]

    form = page.select('.duplicate-group')[1].select_one('form')
    data = {field['name']: field['value'] for field in form.select('input[name]')}
    assert client.post(form['action'], data=data).status_code == 302
    db.session.expire_all()
    assert Company.query.filter_by(slug='microlight3d').first() is None
    assert 'MICROLIGHT3D' in db.session.get(Company, keep).aliases


def test_merge_into_a_company_with_existing_aliases_keeps_the_duplicate_names(db, client, login):
    keep = _add(db, 'Microlight 3D', 'microlight-3d', aliases=['Microlight'])
    _add(db, 'MICROLIGHT3D', 'microlight3d', aliases=['ML3D'], is_auto_created=True)
    login('admin')
    page = BeautifulSoup(client.get('/admin/companies/duplicates').text, 'html.parser')
    form = page.select_one('.duplicate-group form')
    data = {field['name']: field['value'] for field in form.select('input[name]')}
    assert client.post(form['action'], data=data).status_code == 302
    db.session.remove()
    assert db.session.get(Company, keep).aliases == ['Microlight', 'MICROLIGHT3D', 'ML3D']
