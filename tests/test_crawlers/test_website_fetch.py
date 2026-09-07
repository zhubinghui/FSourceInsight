"""Existing website excerpt interface migrated through the real safe HTTP stack."""
import pytest
import requests

from app.utils.website_fetcher import fetch_website_excerpt


@pytest.mark.parametrize('body, status', [('<p>' + 'News ' * 100 + '</p>', 'ok'), ('<div></div>', 'too_thin')])
def test_website_excerpt_keeps_its_text_status_contract(fetch_network, body, status):
    fetch_network.configure(routes={'https://test.invalid/': {'body': body}})
    text, actual = fetch_website_excerpt('https://test.invalid/')
    assert actual == status
    if status == 'ok':
        assert text.startswith('News News') and '<p>' not in text
    else:
        assert text is None


def test_private_website_is_rejected_even_if_old_http_boundary_would_succeed(monkeypatch, fetch_network):
    def old_http(*args, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response._content = ('<p>' + 'private-data ' * 100 + '</p>').encode()
        return response
    monkeypatch.setattr(requests, 'get', old_http)
    assert fetch_website_excerpt('http://169.254.169.254/latest') == (None, 'fetch_error')
    assert not [e for e in fetch_network.events() if e['kind'] == 'connect']


def test_robots_denied_website_does_not_fallback_to_direct_http(fetch_network):
    fetch_network.configure(routes={'https://test.invalid/robots.txt': {'body': 'User-agent: *\nDisallow: /\n'}})
    assert fetch_website_excerpt('https://test.invalid/') == (None, 'http_error')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 1
