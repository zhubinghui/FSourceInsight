"""Long-lived sample provenance via real admin HTTP, not a validation shortcut."""
import hashlib
import json
import pytest
from sqlalchemy import text

from bs4 import BeautifulSoup

from tests.test_web import test_crawl_preview as previews
from tests.test_web import test_crawl_evidence as evidence

source = previews.source
fetch_network = previews.fetch_network
no_dispatch_or_model = previews.no_dispatch_or_model
evidence_dir = evidence.evidence_dir


def capture_page(client, report_url):
    response = client.get(report_url)
    assert response.status_code == 200
    link = BeautifulSoup(response.text, 'html.parser').select_one('a[data-capture-reference]')
    assert link is not None
    response = client.get(link['href'])
    assert response.status_code == 200
    return link['href'], response, BeautifulSoup(response.text, 'html.parser')


def take_preview(client, source_id, csrf_token, fetch_network, *, version=None, retain=False, hosts='news.test.invalid'):
    version = version or previews.save_candidate(client, source_id, csrf_token)
    action, form = previews.preview_form(client, version)
    if 'expected_policy' not in form:
        form.update(allowed_hosts=hosts, quality_kind='news')
    if retain:
        form['retain_evidence'] = '1'
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': previews.FEED, 'headers': {'Content-Type': 'application/rss+xml'},
    }})
    result = client.post(action, data=form)
    assert result.status_code == 302
    return version, result.location


def test_preview_records_private_fingerprints_without_retaining_raw_pages(app, client, source, csrf_token, fetch_network, evidence_dir):
    version, report = take_preview(client, source, csrf_token, fetch_network)
    calls = len(fetch_network.processes)
    with app.app_context():
        _, response, page = capture_page(client, report)
        manifest = json.loads(page.select_one('[data-capture-document]').get_text())
        assert manifest['format'] == 'crawl-capture.v1'
        assert manifest['purpose'] == 'preview'
        assert manifest['recipe_hash']
        assert manifest['source_policy'] is None
        assert manifest['documents'][0]['requested_url_hash'] == hashlib.sha256(b'https://news.test.invalid/feed').hexdigest()
        assert manifest['documents'][0]['document_url_hash'] == hashlib.sha256(b'https://news.test.invalid/feed').hexdigest()
        assert manifest['documents'][0]['snapshot_id'] == 'sha256:' + hashlib.sha256(previews.FEED.encode()).hexdigest()
        assert manifest['documents'][0]['response_bytes'] == len(previews.FEED.encode())
        assert page.select_one('[data-capture-actor]').get_text(strip=True)
        assert page.select_one('[data-capture-created]').get_text(strip=True)
        assert page.select_one('[data-capture-integrity]').get_text(strip=True) == 'available'
        assert 'Grenoble research' not in response.text and 'https://news.test.invalid/feed' not in response.text
        assert 'not independent validation or approval' in response.text
        assert client.get('/api/v1/news').json['total'] == 0
        assert BeautifulSoup(client.get(version).text, 'html.parser').select_one('[data-version-status]').get_text(strip=True) == 'Candidate'
    assert len(fetch_network.processes) == calls
    assert not list(evidence_dir.iterdir())


def history_page(client, source_id):
    root = BeautifulSoup(client.get(f'/admin/sources/{source_id}/crawl-config').text, 'html.parser')
    link = root.select_one('a[data-capture-history-link]')
    assert link is not None
    response = client.get(link['href'])
    assert response.status_code == 200
    return link['href'], response, BeautifulSoup(response.text, 'html.parser')


def test_capture_history_survives_preview_pruning(client, source, csrf_token, fetch_network):
    version, report = take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    first_capture = capture_page(client, report)[0]
    for _ in range(20):
        take_preview(client, source, csrf_token, fetch_network, version=version, hosts='other.test.invalid')
    assert client.get(report).status_code == 404
    assert client.get(first_capture).status_code == 200
    _, _, page = history_page(client, source)
    assert page.select_one('[data-capture-history-state]').get_text(strip=True) == 'tracked'
    assert page.select_one('[data-capture-generation]').get_text(strip=True) == '21'
    assert len(page.select('a[data-capture-entry]')) == 21
    assert page.select_one(f'a[href="{first_capture}"]')
    assert not fetch_network.processes


@pytest.mark.parametrize('damage', ['missing_row', 'reverted_marker', 'sequence_gap', 'untracked_report'])
def test_broken_history_is_not_reported_complete_and_blocks_new_preview(db, client, source, csrf_token, fetch_network, damage):
    version, _ = take_preview(client, source, csrf_token, fetch_network, hosts='other.test.invalid')
    if damage == 'missing_row':
        db.session.execute(text('DELETE FROM crawl_capture_manifest'))
    elif damage == 'reverted_marker':
        db.session.execute(text('UPDATE crawl_source_profile SET capture_generation=0'))
    elif damage == 'sequence_gap':
        db.session.execute(text('UPDATE crawl_capture_manifest SET sequence=9'))
    else:
        db.session.execute(text('UPDATE crawl_capture_manifest SET preview_report_id=999'))
    db.session.commit()
    assert history_page(client, source)[2].select_one('[data-capture-history-state]').get_text(strip=True) == 'unavailable'
    action, form = previews.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    assert client.post(action, data=form).status_code == 409
    assert not fetch_network.processes


@pytest.mark.parametrize('damage', ['bad_hash', 'extra_rehashed', 'binding_rehashed', 'bad_page_rehashed'])
def test_corrupt_manifest_never_exposes_untrusted_metadata(db, client, source, csrf_token, fetch_network, caplog, damage):
    _, report = take_preview(client, source, csrf_token, fetch_network)
    location, _, page = capture_page(client, report)
    document = json.loads(page.select_one('[data-capture-document]').get_text())
    if damage == 'extra_rehashed':
        document['raw_body'] = 'PRIVATE_CAPTURE_BODY<script>alert(1)</script>'
    elif damage == 'binding_rehashed':
        document['version_id'] += 1
    elif damage == 'bad_page_rehashed':
        document['documents'][0]['requested_url_hash'] = 'PRIVATE_CAPTURE_QUERY'
    encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False)
    digest = '0' * 64 if damage == 'bad_hash' else hashlib.sha256(encoded.encode()).hexdigest()
    db.session.execute(text('UPDATE crawl_capture_manifest SET document=:doc,document_hash=:hash'), {'doc': encoded, 'hash': digest})
    db.session.commit()
    calls = len(fetch_network.processes)
    response = client.get(location)
    assert response.status_code == 200
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-capture-integrity]').get_text(strip=True) == 'unavailable'
    assert page.select_one('[data-capture-document]') is None
    assert 'PRIVATE_CAPTURE' not in response.text + caplog.text
    assert len(fetch_network.processes) == calls
