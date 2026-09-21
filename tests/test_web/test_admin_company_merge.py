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


def test_merge_keeps_the_stronger_link_when_both_companies_share_an_article(db, client, login):
    from app.models.article import Article, ArticleCompany
    from app.models.source import NewsSource
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://news.test.invalid/',
                        feed_type='rss', category='national')
    target = Company(name='Orioma', slug='orioma')
    duplicate = Company(name='ORIOMA SAS', slug='orioma-sas')
    db.session.add_all([source, target, duplicate])
    db.session.flush()
    shared = Article(source_id=source.id, title_fr='Shared', url='https://news.test.invalid/a')
    only_duplicate = Article(source_id=source.id, title_fr='Duplicate only', url='https://news.test.invalid/b')
    db.session.add_all([shared, only_duplicate])
    db.session.flush()
    db.session.add_all([
        ArticleCompany(article_id=shared.id, company_id=target.id, sentiment='neutral',
                       mention_count=1, is_primary=False),
        ArticleCompany(article_id=shared.id, company_id=duplicate.id, sentiment='positive',
                       sentiment_score=0.8, mention_count=4, is_primary=True),
        ArticleCompany(article_id=only_duplicate.id, company_id=duplicate.id, sentiment='negative'),
    ])
    db.session.commit()
    target_id, shared_id = target.id, shared.id
    login('admin')
    token = BeautifulSoup(client.get('/admin/companies/merge').text, 'html.parser').select_one(
        'input[name=csrf_token]')['value']

    client.post('/admin/companies/merge',
                data={'csrf_token': token, 'target_id': target_id, 'source_id': duplicate.id})

    db.session.expire_all()
    links = ArticleCompany.query.filter_by(company_id=target_id).all()
    assert len(links) == 2
    kept = next(link for link in links if link.article_id == shared_id)
    # The duplicate knew more about this article; that knowledge must survive the merge.
    assert (kept.sentiment, kept.sentiment_score, kept.mention_count, kept.is_primary) == ('positive', 0.8, 4, True)
    assert ArticleCompany.query.filter_by(company_id=duplicate.id).count() == 0
