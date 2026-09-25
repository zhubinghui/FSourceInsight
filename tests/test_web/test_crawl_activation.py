"""Approval through real Admin forms: evidence, CAS and audit (spec §4.1–4.2)."""
from datetime import timedelta

import pytest
from bs4 import BeautifulSoup

from app.crawlers import schedule
from app.models.crawl_runtime import CrawlSchemaDecision, CrawlSourceState
from app.models.crawl_schema import CrawlSourceProfile
from tests.test_web import test_crawl_policy as policy
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_validation as validation

source = preview.source
fetch_network = preview.fetch_network
evidence_dir = validation.evidence_dir
learning_io = validation.learning_io
model = validation.model


def ready_report(client, source_id, csrf_token, fetch_network):
    policy.save_policy(client, source_id)
    version = preview.save_candidate(client, source_id, csrf_token)
    action, form = preview.preview_form(client, version)
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    response = client.post(action, data=form)
    assert response.status_code == 302
    return version, response.location.rstrip('/').rsplit('/', 1)[1]


def decision_form(client, page_url, selector):
    page = BeautifulSoup(client.get(page_url).text, 'html.parser')
    form = page.select_one(selector)
    assert form is not None
    fields = {item['name']: item.get('value', '') for item in form.select('input[name]')}
    options = [option['value'] for option in form.select('select[name=report_id] option')]
    if options:
        fields['report_id'] = options[0]
    return form['action'], fields


def approved(client, source_id, csrf_token, fetch_network):
    version, _ = ready_report(client, source_id, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 302
    return version


def test_approving_a_current_preview_activates_it_and_schedules_it_now(app, db, client, source, csrf_token, fetch_network):
    version, report_id = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    assert fields['report_id'] == report_id
    requests = len(fetch_network.events())
    assert client.post(action, data=fields).status_code == 302
    assert len(fetch_network.events()) == requests
    with app.app_context():
        page = BeautifulSoup(client.get(version).text, 'html.parser')
        assert page.select_one('[data-version-status]').get_text(strip=True) == 'Active'
        index = BeautifulSoup(client.get(f'/admin/sources/{source}/crawl-config').text, 'html.parser')
        assert index.select_one('[data-active-version]').get_text(strip=True) == version.rsplit('/', 1)[1]
        assert index.select_one('[data-activation-generation]').get_text(strip=True) == '1'
        assert f'preview {report_id}' in index.select_one('[data-decision]').get_text()
        assert client.get('/api/v1/news').json['total'] == 0
    db.session.remove()
    state = db.session.get(CrawlSourceState, source)
    assert state.due_reason == 'activation'


def test_a_second_form_loaded_before_a_decision_is_refused(db, client, source, csrf_token, fetch_network):
    version, _ = ready_report(client, source, csrf_token, fetch_network)
    first = decision_form(client, version, 'form[data-approve]')
    second = decision_form(client, version, 'form[data-reject]')
    assert client.post(first[0], data=first[1]).status_code == 302
    assert client.post(second[0], data=second[1]).status_code == 409
    db.session.remove()
    assert CrawlSchemaDecision.query.count() == 1


@pytest.mark.parametrize('change', ['source_edit', 'too_old', 'policy_revoked'])
def test_stale_or_old_preview_evidence_cannot_approve(db, client, source, csrf_token, fetch_network, monkeypatch, change):
    version, report_id = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    if change == 'source_edit':
        preview.edit_source(client, source, csrf_token, url='https://news.test.invalid/moved')
    elif change == 'too_old':
        later = schedule.now() + timedelta(hours=25)
        monkeypatch.setattr(schedule, 'now', lambda: later)
    else:
        revoke_action, revoke_fields = policy.revoke_form(client, source)
        assert client.post(revoke_action, data=revoke_fields).status_code == 302
    fields['report_id'] = report_id
    assert client.post(action, data=fields).status_code == 409
    db.session.remove()
    assert CrawlSourceProfile.query.filter_by(source_id=source).one().active_version_id is None


def test_a_preview_without_a_saved_policy_is_not_evidence(db, client, source, csrf_token, fetch_network):
    version = preview.save_candidate(client, source, csrf_token)
    action, form = preview.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    report = client.post(action, data=form).location.rstrip('/').rsplit('/', 1)[1]
    approve_action, fields = decision_form(client, version, 'form[data-approve]')
    assert 'report_id' not in fields
    fields['report_id'] = report
    assert client.post(approve_action, data=fields).status_code == 409


def test_rejected_candidates_cannot_be_approved(db, client, source, csrf_token, fetch_network):
    version, report_id = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-reject]')
    fields['reason'] = 'Selectors pick navigation links'
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(version).text, 'html.parser')
    assert page.select_one('[data-version-status]').get_text(strip=True) == 'Rejected'
    approve_action, approve_fields = decision_form(client, version, 'form[data-approve]')
    approve_fields['report_id'] = report_id
    assert client.post(approve_action, data=approve_fields).status_code == 409


@pytest.mark.parametrize('field', ['active_version_id', 'actor_id', 'evidence_hash', 'status'])
def test_decision_forms_reject_server_owned_fields(client, source, csrf_token, fetch_network, field):
    version, _ = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    fields[field] = 'untrusted'
    assert client.post(action, data=fields).status_code == 400


def test_decisions_require_admin_and_csrf(app, db, client, source, csrf_token, fetch_network):
    version, _ = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data={k: v for k, v in fields.items() if k != 'csrf_token'}).status_code == 400
    # An anonymous client is stopped by CSRF or the admin guard; either way nothing is decided.
    assert app.test_client().post(action, data=fields).status_code in (302, 400, 401, 403)
    db.session.remove()
    assert CrawlSchemaDecision.query.count() == 0


def test_learned_candidate_needs_a_passed_holdout(client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = validation.learned(client, source, csrf_token, fetch_network, learning_io, model)
    candidate = BeautifulSoup(client.get(item.location).text, 'html.parser').select_one('a[data-learning-candidate]')['href']
    action, fields = decision_form(client, candidate, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 409
    validation.capture(client, item.base, fetch_network, 'holdout')
    validation.check(client, item)
    action, fields = decision_form(client, candidate, 'form[data-approve]')
    assert client.post(action, data=dict(fields, report_id='1')).status_code == 400
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(candidate).text, 'html.parser')
    assert page.select_one('[data-version-status]').get_text(strip=True) == 'Active'
    index = BeautifulSoup(client.get(f'/admin/sources/{source}/crawl-config').text, 'html.parser')
    assert 'holdout' in index.select_one('[data-decision]').get_text()
