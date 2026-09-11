"""Raw-file and interleaving boundaries of permanent capture metadata."""
import hashlib
import json
import os
import subprocess
import time

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from tests.test_web import test_crawl_capture as captures
from tests.test_web import test_crawl_preview as previews

source = captures.source
fetch_network = captures.fetch_network
no_dispatch_or_model = captures.no_dispatch_or_model
evidence_dir = captures.evidence_dir


def test_capture_reference_cannot_be_swapped_between_reports(db, client, source, csrf_token, fetch_network):
    _, first = captures.take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    _, second = captures.take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    ids = [int(url.rsplit('/', 1)[1]) for url in (first, second)]
    documents = [json.loads(db.session.execute(text('SELECT report FROM crawl_preview_report WHERE id=:id'), {'id': i}).scalar_one()) for i in ids]
    documents[0]['capture_manifest'] = documents[1]['capture_manifest']
    db.session.execute(text('UPDATE crawl_preview_report SET report=:data WHERE id=:id'), {'id': ids[0], 'data': json.dumps(documents[0])})
    db.session.commit()
    page = BeautifulSoup(client.get(first).text, 'html.parser')
    assert page.select_one('a[data-capture-reference]') is None
    assert 'Capture reference unavailable' in page.get_text()


def test_metadata_survives_raw_expiry_cleanup_and_replay(client, source, csrf_token, fetch_network, evidence_dir):
    _, report = captures.take_preview(client, source, csrf_token, fetch_network, retain=True)
    location, _, page = captures.capture_page(client, report)
    original = page.select_one('[data-capture-document]').get_text()
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 200
    assert len(captures.history_page(client, source)[2].select('a[data-capture-entry]')) == 1
    files = list(evidence_dir.glob('*.json'))
    assert len(files) == 1
    for path in files:
        os.utime(path, (time.time() - 25 * 3600, time.time() - 25 * 3600))
    assert client.post(f'/admin/sources/{source}/crawl-config/evidence/cleanup', data={'csrf_token': csrf_token()}).status_code == 302
    assert not list(evidence_dir.glob('*.json'))
    assert client.post(report + '/replay', data={'csrf_token': csrf_token()}).status_code == 409
    assert BeautifulSoup(client.get(location).text, 'html.parser').select_one('[data-capture-document]').get_text() == original


@pytest.mark.parametrize('interleave', ['history_damage', 'source_change', 'another_preview'])
def test_capture_rechecks_after_network_without_holding_business_transaction(app, db, client, source, csrf_token, fetch_network, monkeypatch, interleave):
    version, _ = captures.take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    action, form = previews.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    original, changed = subprocess.Popen, []

    def spawn(command, **kwargs):
        if not changed:
            changed.append(True)
            assert not db.session().in_transaction()
            with app.app_context():
                if interleave == 'history_damage':
                    with db.engine.begin() as conn:
                        conn.execute(text('UPDATE crawl_source_profile SET capture_generation=0'))
                elif interleave == 'source_change':
                    previews.edit_source(client, source, csrf_token, url='https://changed.test.invalid/')
                else:
                    other_form = {**form, 'allowed_hosts': 'other.test.invalid'}
                    assert client.post(action, data=other_form).status_code == 302
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', spawn)
    result = client.post(action, data=form)
    assert changed
    if interleave == 'history_damage':
        assert result.status_code == 409
        assert len(captures.history_page(client, source)[2].select('a[data-capture-entry]')) == 1
    else:
        assert result.status_code == 302
        document = json.loads(captures.capture_page(client, result.location)[2].select_one('[data-capture-document]').get_text())
        assert document['completion_status'] == ('stale' if interleave == 'source_change' else 'ready')
        assert document['source_generation'] == 0
        assert captures.history_page(client, source)[2].select_one('[data-capture-generation]').get_text(strip=True) == ('2' if interleave == 'source_change' else '3')


def test_redirect_query_fingerprints_are_exact_but_never_displayed(client, source, csrf_token, fetch_network, caplog):
    requested = 'https://news.test.invalid/feed?secret=PRIVATE_CAPTURE_QUERY'
    final = 'https://news.test.invalid/final?key=PRIVATE_FINAL_QUERY'
    recipe = previews.recipe_for(source)
    recipe['feed']['url'] = requested
    version = previews.save_candidate(client, source, csrf_token, recipe)
    action, form = previews.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    fetch_network.configure(routes={requested: {'status': 302, 'headers': {'Location': final}}, final: {
        'body': previews.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    saved = client.post(action, data=form)
    assert saved.status_code == 302
    _, response, page = captures.capture_page(client, saved.location)
    document = json.loads(page.select_one('[data-capture-document]').get_text())
    assert document['documents'][0]['requested_url_hash'] == hashlib.sha256(requested.encode()).hexdigest()
    assert document['documents'][0]['document_url_hash'] == hashlib.sha256(final.encode()).hexdigest()
    assert 'PRIVATE_CAPTURE_QUERY' not in response.text + caplog.text
    assert 'PRIVATE_FINAL_QUERY' not in response.text + caplog.text


def test_uncertain_commit_preserves_durable_capture_and_raw_file(db, client, source, csrf_token, fetch_network, evidence_dir, monkeypatch, caplog):
    version = previews.save_candidate(client, source, csrf_token)
    action, form = previews.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news', retain_evidence='1')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': previews.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    original, committed = db.engine.dialect.do_commit, []

    def lose_ack(connection):
        original(connection)
        committed.append(True)
        raise OperationalError('PRIVATE_CAPTURE_COMMIT_ACK', {}, Exception('lost acknowledgment'))

    with monkeypatch.context() as patcher:
        patcher.setattr(db.engine.dialect, 'do_commit', lose_ack)
        response = client.post(action, data=form)
    assert committed
    assert response.status_code == 503
    assert 'PRIVATE_CAPTURE_COMMIT_ACK' not in response.text + caplog.text
    assert len(list(evidence_dir.glob('*.json'))) == 1
    page = BeautifulSoup(client.get(version).text, 'html.parser')
    reports = page.select('a[href*="/previews/"]')
    assert len(reports) == 1
    assert captures.capture_page(client, reports[0]['href'])
    assert captures.history_page(client, source)[2].select_one('[data-capture-history-state]').get_text(strip=True) == 'tracked'
    assert client.post(reports[0]['href'] + '/replay', data={'csrf_token': csrf_token()}).status_code == 200
