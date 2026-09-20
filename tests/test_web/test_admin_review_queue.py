"""Administrators work through discovered entities from the company list."""
from bs4 import BeautifulSoup

from app.models.company import Company


def _add(db, name, **fields):
    company = Company(name=name, slug=name.lower().replace(' ', '-').replace("'", ''), is_grenoble=True, **fields)
    db.session.add(company)
    db.session.commit()
    return company.id


def _list(client, **query):
    response = client.get('/admin/companies', query_string=query)
    assert response.status_code == 200
    return BeautifulSoup(response.text, 'html.parser')


def _names(page):
    return [cell.get_text(strip=True) for cell in page.select('tbody tr td:first-child a')]


def _review(client, page, name, status):
    form = next(f for f in page.select('form[action$="/review"]')
                if f.find_parent('tr').select_one('td a').get_text(strip=True) == name
                and f.select_one('input[name=status]')['value'] == status)
    data = {field['name']: field['value'] for field in form.select('input[name]')}
    return client.post(form['action'], data=data)


def test_pending_queue_lists_only_entries_waiting_for_review(db, client, login):
    _add(db, 'Approved Chips')
    _add(db, 'Pending Sensors', review_status='pending')
    _add(db, 'Pending Lasers', review_status='pending')
    login('admin')

    assert 'Pending (2)' in _list(client).get_text(' ', strip=True)
    assert _names(_list(client, review='pending')) == ['Pending Lasers', 'Pending Sensors']


def test_approve_and_reject_from_the_queue(db, client, login):
    _add(db, 'Pending Sensors', review_status='pending')
    _add(db, 'From Tuesday April 07', review_status='pending')
    login('admin')
    queue = _list(client, review='pending')

    approved = _review(client, queue, 'Pending Sensors', 'approved')
    _review(client, queue, 'From Tuesday April 07', 'rejected')

    assert approved.status_code == 302 and approved.headers['Location'].endswith('/admin/companies?review=pending')
    assert _names(_list(client, review='pending')) == []
    assert _names(_list(client, review='rejected')) == ['From Tuesday April 07']
    public = client.get('/companies/').text
    assert 'Pending Sensors' in public and 'From Tuesday April 07' not in public


def test_review_refuses_unknown_status_and_non_admins(db, client, login):
    company_id = _add(db, 'Pending Sensors', review_status='pending')
    login('admin')
    token = _list(client).select_one('input[name=csrf_token]')['value']
    assert client.post(f'/admin/companies/{company_id}/review',
                       data={'csrf_token': token, 'status': 'published'}).status_code == 400

    client.get('/auth/logout')
    login('owner')
    client.post(f'/admin/companies/{company_id}/review', data={'csrf_token': token, 'status': 'approved'})
    assert db.session.get(Company, company_id).review_status == 'pending'


def test_search_filters_and_pagination_keeps_them(db, client, login):
    for number in range(55):
        _add(db, f'Alpha {number:02d}', review_status='pending')
    _add(db, 'Beta Only', review_status='pending')
    login('admin')

    page = _list(client, review='pending', q='alpha')

    assert 'Beta Only' not in _names(page) and len(_names(page)) == 50
    links = [a['href'] for a in page.select('.pagination a')]
    assert links and all('review=pending' in href and 'q=alpha' in href for href in links)


def test_delete_confirmation_does_not_interpolate_names_into_script(db, client, login):
    _add(db, "L'Exemple'); alert(1); ('")
    login('admin')

    form = _list(client).select_one('form[action$="/delete"]')

    assert "Exemple" not in form['onsubmit']
    assert "L'Exemple'); alert(1); ('" in form['data-confirm']


def test_other_admin_delete_confirmations_keep_names_out_of_script(db, client, login, users):
    from app.models.sector_group import SectorGroup
    from app.models.startup_source import StartupSource
    hostile = "L'Exemple'); alert(1); ('"
    db.session.add_all([SectorGroup(name=hostile, icon='cpu', color='#000000', keywords=[], sort_order=1),
                        StartupSource(name=hostile, url='https://directory.test/')])
    db.session.commit()
    login('admin')

    for path in ['/admin/sector-groups', '/admin/startup-sources', '/admin/users']:
        page = BeautifulSoup(client.get(path).text, 'html.parser')
        forms = page.select('form[action$="/delete"]')
        assert forms, path
        for form in forms:
            assert form['onsubmit'] == 'return confirm(this.dataset.confirm)', path
            assert form['data-confirm'].startswith('Delete '), path
