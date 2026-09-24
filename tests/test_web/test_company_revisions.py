"""Company analysis revisions through real admin HTTP edits and a fresh read."""
from bs4 import BeautifulSoup

from app.extensions import db
from app.models.company import Company

SLUG = 'revision-synthetic'


def edit(client, overview):
    path = f'/companies/{SLUG}/edit-analysis'
    token = BeautifulSoup(client.get(path).text, 'html.parser').select_one('input[name=csrf_token]')['value']
    assert client.post(path, data={'csrf_token': token, 'overview': overview}).status_code == 302


def stored():
    db.session.remove()
    return db.session.query(Company).filter_by(slug=SLUG).one()


def test_every_consecutive_edit_is_kept_in_the_revision_history(client, login):
    db.session.add(Company(name='Revision Synthetic', slug=SLUG, ai_analysis={'overview': 'v0'},
                           ai_revision_history=[{'timestamp': '2026-09-01T00:00:00', 'source': 'seed',
                                                 'trigger': '', 'changes': []}]))
    db.session.commit()
    assert login('admin').status_code == 302
    edit(client, 'v1')
    edit(client, 'v2')
    company = stored()
    assert company.ai_analysis['overview'] == 'v2'
    assert [item['source'] for item in company.ai_revision_history] == ['seed', 'manual-edit', 'manual-edit']
    assert company.ai_revision_history[-1]['changes'][0]['old'] == 'v1'


def test_history_keeps_only_the_latest_ten_entries(client, login):
    seed = [{'timestamp': f'2026-09-01T00:00:0{i}', 'source': f'seed-{i}', 'trigger': '', 'changes': []}
            for i in range(10)]
    db.session.add(Company(name='Revision Synthetic', slug=SLUG, ai_analysis={'overview': 'v0'},
                           ai_revision_history=seed))
    db.session.commit()
    assert login('admin').status_code == 302
    edit(client, 'v1')
    history = stored().ai_revision_history
    assert len(history) == 10
    assert history[0]['source'] == 'seed-1' and history[-1]['source'] == 'manual-edit'
