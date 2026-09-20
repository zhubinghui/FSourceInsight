"""Both released review controls and M3 source-owned analysis at public seams."""
import subprocess

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import Company
from app.models.startup_source import StartupSource
from app.llm.startup_tasks import analyze
from tests.test_crawlers import test_startup_analysis as base
from tests.test_crawlers.test_startup_reliability import prepared, state


discovery = base.discovery
DETAIL = 'https://directory.example.test/member-directory/alpine/'
FACTS = '<p>Type of Organization SME Themes Sensors</p><p>Contact details Adress 1 Rue Test 69001 LYON Contact Website</p>'


def test_directory_facts_are_kept_without_approved_publication_or_inline_model(discovery):
    discovery.network.configure(routes={
        base.URL: {'body': f'<a href="{DETAIL}">Alpine Synthetic</a>'},
        DETAIL: {'body': FACTS},
    })
    base.add_source(discovery)
    base.scan(discovery)
    row = db.session.query(Company).one()
    assert (row.review_status, row.postcode, row.city, row.entity_type, row.is_grenoble) == (
        'pending', '69001', 'Lyon', 'company', False)
    assert len(base.jobs(discovery)) == 1 and not discovery.calls
    assert b'Alpine Synthetic' not in discovery.client.get('/companies/').data
    identity = base.jobs(discovery)[0].decode()
    analyze.run(identity)
    db.session.remove()
    row = db.session.query(Company).one()
    assert row.ai_analysis['overview'] == base.RESULT['overview']
    assert row.review_status == 'pending' and row.postcode == '69001'
    assert len(discovery.calls) == 1


@pytest.mark.parametrize('in_flight', [False, True])
def test_manual_review_invalidates_original_analysis_intent(discovery, monkeypatch, in_flight):
    _, identity = prepared(discovery)
    company_id = db.session.query(Company).one().id
    def reject():
        token = discovery.csrf('/admin/companies')
        assert discovery.client.post(f'/admin/companies/{company_id}/review', data={
            'csrf_token': token, 'status': 'rejected'}).status_code == 302
    if in_flight:
        def provider(**kwargs):
            reject()
            return discovery.complete(**kwargs)
        monkeypatch.setattr(discovery.provider.litellm, 'completion', provider)
    else:
        reject()
    analyze.run(identity)
    db.session.remove()
    row = db.session.get(Company, company_id)
    assert row.review_status == 'rejected' and row.ai_analysis is None
    assert state(discovery, identity) == 'stale'
    assert len(discovery.calls) == int(in_flight)


def test_structured_discovery_keeps_the_thousand_entry_bound(discovery):
    body = ''.join(f'<div data-name="Synthetic {n}" data-description="Synthetic"></div>' for n in range(1100))
    discovery.network.configure(routes={base.URL: {'body': body}})
    source = base.add_source(discovery)
    base.scan(discovery)
    assert db.session.get(StartupSource, source).companies_found == 1000
    assert len(base.jobs(discovery)) == 20 and not discovery.calls


def test_directory_detail_http_does_not_hold_the_accounting_write_gate(discovery, monkeypatch):
    discovery.network.configure(routes={
        base.URL: {'body': f'<a href="{DETAIL}">Alpine Synthetic</a>'}, DETAIL: {'body': FACTS},
    })
    base.add_source(discovery)
    gate, launches = [False], []
    def writing(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO llm_budget_gate '):
            gate[0] = True
    def committed(session):
        gate[0] = False
    original = subprocess.Popen
    def launch(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and any(str(part).endswith('_fetch_worker.py') for part in command):
            launches.append(True)
            assert not gate[0], 'Directory HTTP cannot hold flushed business/accounting writes'
        return original(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    event.listen(db.engine, 'before_cursor_execute', writing)
    event.listen(Session, 'after_commit', committed)
    try:
        base.scan(discovery)
    finally:
        event.remove(db.engine, 'before_cursor_execute', writing)
        event.remove(Session, 'after_commit', committed)
    assert len(launches) >= 2
    assert db.session.query(Company).one().postcode == '69001'
    assert len(base.jobs(discovery)) == 1


def test_directory_link_does_not_expand_the_configured_host_permission(discovery):
    other = 'https://unapproved.example.test/member-directory/elsewhere/'
    discovery.network.configure(routes={base.URL: {'body': f'<a href="{other}">Alpine Synthetic</a>'},
                                        other: {'body': FACTS}})
    base.add_source(discovery)
    base.scan(discovery)
    assert all(event.get('host') != 'unapproved.example.test' for event in discovery.network.events())
    row = db.session.query(Company).one()
    assert row.review_status == 'pending' and row.postcode is None
    assert not discovery.calls
