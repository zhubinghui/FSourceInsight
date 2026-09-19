"""Learning-history authority through real Admin HTTP and the learning task."""
import json
import pytest
from sqlalchemy import text
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


def learned(client, source, csrf_token, fetch_network, learning_io, model):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    assert started.status_code == 302
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    return started.location


def test_admin_sees_complete_workflow_history_and_safe_exposure_fingerprints(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    location = learned(client, source, csrf_token, fetch_network, learning_io, model)
    response = client.get(location)
    page = BeautifulSoup(response.text, 'html.parser')
    coverage = page.select_one('[data-learning-history]')
    assert coverage is not None
    assert coverage.get_text(strip=True) == 'tracked'
    assert page.select_one('[data-history-sessions]').get_text(strip=True) == '1'
    assert page.select_one('[data-history-exposures]').get_text(strip=True) == '1'
    documents = json.loads(page.select_one('[data-exposure-document]').get_text())
    assert len(documents) == 1
    assert len(documents[0]['text_hash']) == 64
    assert documents[0]['text_version'] == 'visible-text.v1'
    assert len(page.select_one('[data-exposure-hash]').get_text(strip=True)) == 64
    assert 'Grenoble laboratory' not in response.text
    assert 'Not independently validated' in page.get_text()
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/v1/news').json['total'] == 0


@pytest.mark.parametrize('loss', ['session', 'attempt', 'marker', 'reverted_marker'])
def test_missing_past_history_blocks_another_session_before_payment(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, loss):
    old = learned(client, source, csrf_token, fetch_network, learning_io, model)
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    assert started.status_code == 302
    with db.engine.begin() as conn:
        if loss == 'session':
            conn.execute(text('DELETE FROM crawl_repair_attempt WHERE session_id=:id'), {'id': old.rsplit('/', 1)[1]})
            conn.execute(text('DELETE FROM crawl_repair_session WHERE id=:id'), {'id': old.rsplit('/', 1)[1]})
        elif loss == 'attempt':
            conn.execute(text('DELETE FROM crawl_repair_attempt WHERE session_id=:id'), {'id': old.rsplit('/', 1)[1]})
        elif loss == 'marker':
            conn.execute(text('DELETE FROM crawl_learning_history'))
        else:
            conn.execute(text('UPDATE crawl_learning_history SET exposure_generation=0'))
    response = client.get(started.location)
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'unavailable'
    base.deliver(learning_io)
    assert len(model.provider.calls) == 1
    assert base.state(client, started.location) == 'blocked'
    assert client.post(action, data=fields).status_code == 409


@pytest.mark.parametrize('damage', ['text_hash', 'private_field', 'exposure_hash', 'prompt_hash', 'input_hash', 'deadline'])
def test_corrupt_historical_input_or_exposure_is_not_tracked_and_blocks_payment(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, damage):
    old = learned(client, source, csrf_token, fetch_network, learning_io, model)
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    current = client.post(action, data=fields)
    old_id = old.rsplit('/', 1)[1]
    with db.engine.begin() as conn:
        if damage in ('text_hash', 'private_field'):
            raw = conn.execute(text('SELECT exposure FROM crawl_repair_attempt WHERE session_id=:id'), {'id': old_id}).scalar_one()
            pages = json.loads(raw)
            pages[0]['text_hash' if damage == 'text_hash' else 'private'] = '0' * 64 if damage == 'text_hash' else 'PRIVATE_HISTORY_PAYLOAD<script>alert(1)</script>'
            conn.execute(text('UPDATE crawl_repair_attempt SET exposure=:value WHERE session_id=:id'),
                         {'value': json.dumps(pages), 'id': old_id})
        elif damage in ('exposure_hash', 'prompt_hash'):
            conn.execute(text(f'UPDATE crawl_repair_attempt SET {damage}=:value WHERE session_id=:id'), {'value': '0' * 64, 'id': old_id})
        elif damage == 'input_hash':
            conn.execute(text('UPDATE crawl_repair_session SET input_hash=:value WHERE id=:id'), {'value': '0' * 64, 'id': old_id})
        else:
            conn.execute(text("UPDATE crawl_repair_session SET deadline_at='2099-01-01 00:00:00' WHERE id=:id"), {'id': old_id})
    response = client.get(old)
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'unavailable'
    assert 'PRIVATE_HISTORY_PAYLOAD' not in response.text
    base.deliver(learning_io)
    assert base.state(client, current.location) == 'blocked'
    assert len(model.provider.calls) == 1


def test_text_fingerprint_recognizes_rewrapped_copy_without_url_or_raw_byte_equality(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    import hashlib
    from tests.test_web import test_crawl_preview as preview
    base.policy.save_policy(client, source)
    fingerprints = []
    for index, body in enumerate([
        '<article><a href="/one">Grenoble research</a><p>Ａura research body is identical in both documents.</p></article>',
        '<main><article data-id="two"><a href="/two">Another Grenoble report</a><p>aura   RESEARCH <b>body</b> is identical in both documents.</p></article><footer>Different footer</footer></main>',
    ]):
        recipe = recipe_for(source)
        recipe.pop('feed')
        recipe.update(extractor='html', list_pages=[{'url': f'https://news.test.invalid/list-{index}',
            'item_selector': 'article', 'fields': {'title': {'selector': 'a', 'read': 'text'},
            'url': {'selector': 'a', 'read': 'attr', 'attr': 'href'}}}])
        version = preview.save_candidate(client, source, csrf_token, recipe)
        action, fields = preview.preview_form(client, version)
        fetch_network.configure(routes={recipe['list_pages'][0]['url']: {'body': body}})
        report = client.post(action, data={**fields, 'retain_evidence': '1'})
        assert report.status_code == 302
        action, fields = base.form_at(client, report.location, 'form[data-learning-start]')
        started = client.post(action, data=fields)
        assert started.status_code == 302
        model.provider.reply = recipe
        base.deliver(learning_io)
        response = client.get(started.location)
        page = BeautifulSoup(response.text, 'html.parser')
        assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
        fingerprints.append(json.loads(page.select_one('[data-exposure-document]').get_text())[0])
        assert 'identical in both documents' not in response.text
    assert fingerprints[0]['snapshot_id'] != fingerprints[1]['snapshot_id']
    assert fingerprints[0]['document_url_hash'] != fingerprints[1]['document_url_hash']
    expected = hashlib.sha256(b'aura research body is identical in both documents.').hexdigest()
    assert fingerprints[0]['text_hash'] == fingerprints[1]['text_hash'] == expected


def test_history_capacity_refuses_new_sessions_without_poisoning_existing_coverage(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    app.config['CRAWL_LEARNING_HISTORY_SCAN_LIMIT'] = 2
    first = learned(client, source, csrf_token, fetch_network, learning_io, model)
    learned(client, source, csrf_token, fetch_network, learning_io, model)
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    assert client.post(action, data=fields).status_code == 409
    page = BeautifulSoup(client.get(first).text, 'html.parser')
    assert page.select_one('[data-learning-history]').get_text(strip=True) == 'tracked'
    assert page.select_one('[data-history-sessions]').get_text(strip=True) == '2'
    assert len(model.provider.calls) == 2
