"""Merging a duplicate keeps what only the duplicate knew."""
from bs4 import BeautifulSoup

from app.models.company import Company


def test_merge_fills_empty_target_fields_and_keeps_target_values(db, client, login):
    target = Company(name='Microlight 3D', slug='microlight-3d', sector='MedTech / Health')
    source = Company(name='MICROLIGHT3D', slug='microlight3d', is_grenoble=True, sector='Photonics',
                     website='https://microlight.example', postcode='38700', city='La Tronche',
                     entity_type='company', description='Two-photon 3D printing',
                     ai_analysis={'overview': 'duplicate analysis'})
    db.session.add_all([target, source])
    db.session.commit()
    target_id, source_id = target.id, source.id
    login('admin')
    token = BeautifulSoup(client.get('/admin/companies/merge').text, 'html.parser').select_one(
        'input[name=csrf_token]')['value']

    response = client.post('/admin/companies/merge',
                           data={'csrf_token': token, 'target_id': target_id, 'source_id': source_id})

    assert response.status_code == 302
    db.session.expire_all()
    merged = db.session.get(Company, target_id)
    assert db.session.get(Company, source_id) is None
    assert merged.sector == 'MedTech / Health'
    assert (merged.website, merged.postcode, merged.city, merged.entity_type, merged.description) == (
        'https://microlight.example', '38700', 'La Tronche', 'company', 'Two-photon 3D printing')
    assert merged.ai_analysis == {'overview': 'duplicate analysis'}
    assert merged.is_grenoble is True
    assert 'MICROLIGHT3D' in merged.aliases
