"""Public SafeFetcher tests: all HTTP/DNS/TLS are synthetic, not bypassed."""
import ssl
import time

import pytest


def test_authorized_https_preserves_host_tls_and_returns_evidence(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        result = fetcher.fetch('https://news.test.invalid/news')
        assert result.body == b'<p>Bonjour</p>'
        assert result.observation.status == 'ok'
        assert result.observation.final_url == 'https://news.test.invalid/news'
        assert result.observation.snapshot_id.startswith('sha256:')
    events = fetch_network.events()
    assert [e['url'] for e in events if e['kind'] == 'http'] == [
        'https://news.test.invalid/robots.txt', 'https://news.test.invalid/news',
    ]
    assert all(e['ip'] == '93.184.216.34' for e in events if e['kind'] == 'connect')
    assert any(e['kind'] == 'tls' and e['hostname'] == 'news.test.invalid'
               and e['verify_mode'] == ssl.CERT_REQUIRED for e in events)
    assert all(p.poll() is not None for p in fetch_network.processes)


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'gopher://news.test.invalid/', 'https://u:p@news.test.invalid/',
    'https://other.test.invalid/', 'https://news.test.invalid:22/', 'http://127.0.0.1/',
    'http://2130706433/', 'http://127.1/', 'http://0x7f000001/', 'http://169.254.169.254/',
    'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'http://[fe80::1%25lo0]/',
    'https://news.test.invalid/\nprivate', 'https://news.test.invalid\\@127.0.0.1/',
])
def test_unsafe_urls_never_send_http(fetch_network, url):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError) as error:
            fetcher.fetch(url)
        assert error.value.code == 'unsafe_url'
    assert not [e for e in fetch_network.events() if e['kind'] == 'http']


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.1.2.3', '169.254.169.254', '100.64.0.1',
                                '224.0.0.1', '::1', 'fc00::1', '::ffff:127.0.0.1',
                                '64:ff9b::7f00:1', '2002:7f00:1::'])
def test_any_non_public_dns_answer_blocks_before_connect(fetch_network, ip):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(dns={'news.test.invalid': ['93.184.216.34', ip]})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError) as error:
            fetcher.fetch('https://news.test.invalid/news')
        assert error.value.code == 'unsafe_url'
    assert not [e for e in fetch_network.events() if e['kind'] == 'connect']


@pytest.mark.parametrize('values', [
    {'allowed_hosts': []}, {'allowed_hosts': '*'}, {'allowed_hosts': ['*.invalid']},
    {'max_seconds': True}, {'max_seconds': 0}, {'max_seconds': float('nan')},
])
def test_system_policy_is_validated_not_silently_coerced(values):
    from app.crawlers.fetcher import FetchPolicy

    with pytest.raises(ValueError):
        FetchPolicy(**({'allowed_hosts': ['news.test.invalid']} | values))


@pytest.mark.parametrize('stage', ['dns', 'headers', 'body'])
def test_deadline_kills_blocked_io_and_never_reuses_the_worker(fetch_network, stage):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    if stage == 'dns':
        fetch_network.configure(dns_delay=60)
    else:
        fetch_network.configure(routes={'https://news.test.invalid/news': {
            'delay' if stage == 'headers' else 'body_delay': 60}})
    start = time.monotonic()
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_seconds=1)) as fetcher:
        with pytest.raises(FetchError, match='timeout'):
            fetcher.fetch('https://news.test.invalid/news')
        assert all(p.poll() is not None for p in fetch_network.processes)
        with pytest.raises(FetchError, match='fetch_closed'):
            fetcher.fetch('https://news.test.invalid/other')
    assert time.monotonic() - start < 3
    assert len(fetch_network.processes) == 1


def test_expired_run_does_not_even_start_a_helper(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_seconds=0.05)) as fetcher:
        time.sleep(0.06)
        with pytest.raises(FetchError, match='timeout'):
            fetcher.fetch('https://news.test.invalid/news')
    assert not fetch_network.processes


@pytest.mark.parametrize('target', ['http://news.test.invalid/down', 'https://other.test.invalid/',
                                    'http://127.0.0.1/', 'https://news.test.invalid:22/'])
def test_each_redirect_is_checked_before_following(fetch_network, target):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'status': 302, 'headers': {'Location': target}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='unsafe_url'):
            fetcher.fetch('https://news.test.invalid/news')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 2


def test_redirect_to_explicitly_allowed_host_rechecks_robots_and_strips_cookies(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'status': 302, 'headers': {'Location': 'https://www.test.invalid/article', 'Set-Cookie': 'token=secret'}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid', 'www.test.invalid'))) as fetcher:
        result = fetcher.fetch('https://news.test.invalid/news')
        assert result.observation.final_url == 'https://www.test.invalid/article'
    http = [e for e in fetch_network.events() if e['kind'] == 'http']
    assert [e['url'] for e in http] == ['https://news.test.invalid/robots.txt',
                                      'https://news.test.invalid/news',
                                      'https://www.test.invalid/robots.txt',
                                      'https://www.test.invalid/article']
    assert all('Cookie' not in e['headers'] and 'Authorization' not in e['headers'] for e in http)


@pytest.mark.parametrize('status, code, retryable', [(403, 'forbidden', False), (429, 'rate_limited', True),
                                                     (503, 'server_error', True), (404, 'http_error', False)])
def test_http_failures_are_classified_without_hidden_retries(fetch_network, status, code, retryable):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'status': status}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError) as error:
            fetcher.fetch('https://news.test.invalid/news')
        assert error.value.code == code and error.value.retryable == retryable
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 2


def test_wrong_tls_hostname_is_not_accepted(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(cert_host='wrong.test.invalid')
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='tls_error'):
            fetcher.fetch('https://news.test.invalid/news')
    assert not [e for e in fetch_network.events() if e['kind'] == 'http']


@pytest.mark.parametrize('kind', ['wire', 'decoded', 'mime', 'broken_gzip', 'encoding'])
def test_response_limits_and_encoding_are_enforced_before_return(fetch_network, kind):
    import base64
    import gzip
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    spec = {'body': 'x' * 65}
    code = 'too_large'
    if kind == 'decoded':
        spec = {'body_b64': base64.b64encode(gzip.compress(b'x' * 10000)).decode(),
                'headers': {'Content-Encoding': 'gzip'}}
    elif kind == 'mime':
        spec = {'body': 'x', 'headers': {'Content-Type': 'text/html,application/json'}}
        code = 'unsupported_content_type'
    elif kind in {'broken_gzip', 'encoding'}:
        spec = {'body': 'x', 'headers': {'Content-Encoding': 'gzip' if kind == 'broken_gzip' else 'br'}}
        code = 'decode_error'
    fetch_network.configure(routes={'https://news.test.invalid/news': spec})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_wire_bytes=64,
                                 max_response_bytes=64)) as fetcher:
        with pytest.raises(FetchError, match=code):
            fetcher.fetch('https://news.test.invalid/news')


def test_valid_gzip_and_shared_total_budget_across_fetch_calls(fetch_network):
    import base64
    import gzip
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body_b64': base64.b64encode(gzip.compress(b'hello' * 10)).decode(),
        'headers': {'Content-Encoding': 'gzip'}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_total_bytes=60)) as fetcher:
        assert fetcher.fetch('https://news.test.invalid/news').body == b'hello' * 10
        with pytest.raises(FetchError, match='too_large'):
            fetcher.fetch('https://news.test.invalid/news')


def test_request_budget_includes_robots_and_does_not_reset(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_requests=2)) as fetcher:
        fetcher.fetch('https://news.test.invalid/news')
        with pytest.raises(FetchError, match='budget_exceeded'):
            fetcher.fetch('https://news.test.invalid/second')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 2


@pytest.mark.parametrize('path', ['/private/secret', '/private/%73ecret', '/private%2fhidden'])
def test_robots_disallow_is_checked_with_wildcards_and_normalized_paths(fetch_network, path):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    robots = 'User-agent: *\nDisallow: /private/*\nDisallow: /private%2Fhidden\nAllow: /private/public$\n'
    fetch_network.configure(routes={'https://news.test.invalid/robots.txt': {'body': robots}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='robots_denied'):
            fetcher.fetch('https://news.test.invalid' + path)
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 1


def test_robots_specific_agent_and_longest_allow_rule_work(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    robots = 'User-agent: *\nDisallow: /\n\nUser-agent: FSourceInsightBot\nDisallow: /private/\nAllow: /private/public$\n'
    fetch_network.configure(routes={'https://news.test.invalid/robots.txt': {'body': robots}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        assert fetcher.fetch('https://news.test.invalid/private/public').body


@pytest.mark.parametrize('status, code', [(403, 'robots_denied'), (503, 'server_error')])
def test_failed_robots_does_not_grant_access(fetch_network, status, code):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/robots.txt': {'status': status}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match=code):
            fetcher.fetch('https://news.test.invalid/news')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 1


def test_retry_after_blocks_more_requests_in_the_same_run(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'status': 429, 'headers': {'Retry-After': '3600'}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        for _ in range(2):
            with pytest.raises(FetchError) as error:
                fetcher.fetch('https://news.test.invalid/news')
            assert error.value.code == 'rate_limited' and 3590 <= error.value.retry_after <= 3600
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 2


def test_rebinding_after_robots_cannot_reuse_a_previously_valid_connection(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(dns={'news.test.invalid': [['93.184.216.34'], ['127.0.0.1']]})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='unsafe_url'):
            fetcher.fetch('https://news.test.invalid/news')
    assert [e['ip'] for e in fetch_network.events() if e['kind'] == 'connect'] == ['93.184.216.34']
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 1


def test_no_content_length_does_not_remove_the_byte_limit(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'no_length': True, 'body': 'x' * 200}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_wire_bytes=64)) as fetcher:
        with pytest.raises(FetchError, match='too_large'):
            fetcher.fetch('https://news.test.invalid/news')


def test_redirect_cycle_is_bounded(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'status': 302, 'headers': {'Location': '/news'}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='redirect_limit'):
            fetcher.fetch('https://news.test.invalid/news')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 2


def test_render_request_is_explicitly_unavailable_without_http(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='render_unavailable'):
            fetcher.fetch('https://news.test.invalid/news', transport='browser')
    assert not fetch_network.processes


def test_query_is_private_to_document_resolution_not_observations_or_repr(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    url = 'https://news.test.invalid/news?token=synthetic-secret'
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        result = fetcher.fetch(url)
        assert result.document_url == url
        assert result.observation.final_url == 'https://news.test.invalid/news'
        assert result.observation.requested_url == 'https://news.test.invalid/news'
        assert 'synthetic-secret' not in repr(result)


def test_helper_has_its_own_deadline_if_parent_polling_is_delayed(fetch_network, monkeypatch):
    import selectors
    import signal
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(dns_delay=60)
    original = selectors.DefaultSelector.select
    calls = 0
    def delayed_poll(selector, timeout=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            time.sleep(1.3)
            return original(selector, 0)
        return original(selector, timeout)
    monkeypatch.setattr(selectors.DefaultSelector, 'select', delayed_poll)
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_seconds=1)) as fetcher:
        with pytest.raises(FetchError):
            fetcher.fetch('https://news.test.invalid/news')
    assert fetch_network.processes[0].returncode == -signal.SIGALRM


def test_exhausted_total_budget_stops_before_another_request(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_total_bytes=14)) as fetcher:
        assert len(fetcher.fetch('https://news.test.invalid/news').body) == 14
        with pytest.raises(FetchError, match='budget_exceeded'):
            fetcher.fetch('https://news.test.invalid/next')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 2


def test_chunk_trailers_cannot_bypass_download_limits_with_an_empty_entity(fetch_network):
    import base64
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    framing = b'0\r\n' + (b'X-Trailer: ' + b'x' * 4096 + b'\r\n') * 32 + b'\r\n'
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body_b64': base64.b64encode(framing).decode(), 'no_length': True,
        'headers': {'Transfer-Encoding': 'chunked'},
    }})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_wire_bytes=64)) as fetcher:
        with pytest.raises(FetchError, match='too_large'):
            fetcher.fetch('https://news.test.invalid/news')


@pytest.mark.parametrize('mime', ['text/html;charset="unterminated', 'text/html;charset=\x00utf8'])
def test_malformed_mime_parameters_are_not_accepted(fetch_network, mime):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'headers': {'Content-Type': mime}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='unsupported_content_type'):
            fetcher.fetch('https://news.test.invalid/news')


@pytest.mark.parametrize('path', ['/public/../private', '/public/%2e%2e/private'])
def test_robots_checks_the_path_the_http_client_will_actually_send(fetch_network, path):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/robots.txt': {'body': 'User-agent: *\nDisallow: /private\n'}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='robots_denied'):
            fetcher.fetch('https://news.test.invalid' + path)
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 1


@pytest.mark.parametrize('spec', [{'body': '{"error":"temporarily unavailable"}'}, {'status': 304}])
def test_unavailable_robots_never_becomes_an_allow_all_rule(fetch_network, spec):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/robots.txt': spec})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='robots_unavailable'):
            fetcher.fetch('https://news.test.invalid/news')
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 1


def test_old_transport_api_fails_closed_instead_of_using_unpinned_pools(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(legacy_adapter=True)
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='transport_unavailable'):
            fetcher.fetch('https://news.test.invalid/news')
    assert not [e for e in fetch_network.events() if e['kind'] == 'connect']


def test_raw_body_socket_timeout_is_classified_without_leaking_exception_text(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'body_timeout': True}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError) as error:
            fetcher.fetch('https://news.test.invalid/news')
        assert error.value.code == 'timeout' and error.value.retryable
        assert 'Synthetic' not in str(error.value)


def test_policy_cannot_be_swapped_during_a_run(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(AttributeError):
            fetcher.policy = FetchPolicy(allowed_hosts=('other.test.invalid',))


def test_url_limit_applies_after_percent_encoding_before_network(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='unsafe_url'):
            fetcher.fetch('https://news.test.invalid/' + 'é' * 400)
    assert not fetch_network.processes


def test_forgotten_network_fixture_cannot_spawn_a_real_http_helper():
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(AssertionError, match='fetch_network'):
            fetcher.fetch('https://news.test.invalid/news')


def test_peer_mismatch_stops_before_tls_or_http(fetch_network):
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    fetch_network.configure(peer_ip='127.0.0.1')
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        with pytest.raises(FetchError, match='unsafe_url'):
            fetcher.fetch('https://news.test.invalid/news')
    assert not [e for e in fetch_network.events() if e['kind'] in {'tls', 'http'}]


def test_slow_dns_does_not_consume_the_servers_minimum_request_interval(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    fetch_network.configure(dns_delays=[0.15])
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), min_interval=0.05)) as fetcher:
        fetcher.fetch('https://news.test.invalid/news')
    times = [e['at'] for e in fetch_network.events() if e['kind'] == 'http']
    assert times[1] - times[0] >= 0.05


def test_gzip_bomb_is_stopped_before_allocating_the_expanded_body(fetch_network):
    import base64
    import gzip
    from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

    bomb = gzip.compress(b'A' * (16 * 1024 * 1024))
    fetch_network.configure(measure_memory=True, routes={'https://news.test.invalid/news': {
        'body_b64': base64.b64encode(bomb).decode(), 'headers': {'Content-Encoding': 'gzip'},
    }})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',), max_response_bytes=1024)) as fetcher:
        with pytest.raises(FetchError, match='too_large'):
            fetcher.fetch('https://news.test.invalid/news')
    peak = next(e['peak'] for e in fetch_network.events() if e['kind'] == 'memory')
    assert peak < 2 * 1024 * 1024


def test_helper_does_not_inherit_proxy_home_or_application_credentials(fetch_network, monkeypatch):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:9999')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'synthetic-secret')
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        assert fetcher.fetch('https://news.test.invalid/news').body
    keys = next(e['keys'] for e in fetch_network.events() if e['kind'] == 'environment')
    assert not {'HTTPS_PROXY', 'HOME', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY'} & set(keys)


@pytest.mark.parametrize('mime, body', [
    ('text/html; charset="utf-8"', '<p>Bonjour</p>'),
    ('application/ld+json', '{"@type":"NewsArticle"}'),
    ('application/atom+xml', '<feed xmlns="http://www.w3.org/2005/Atom"/>'),
])
def test_supported_mime_variants_remain_usable(fetch_network, mime, body):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': body, 'headers': {'Content-Type': mime}}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        assert fetcher.fetch('https://news.test.invalid/news').body == body.encode()


def test_not_modified_has_no_new_body_or_snapshot(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    fetch_network.configure(routes={'https://news.test.invalid/news': {'status': 304}})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        result = fetcher.fetch('https://news.test.invalid/news')
        assert result.body == b'' and result.observation.status == 'not_modified'
        assert result.observation.snapshot_id is None


def test_global_ipv6_dns_address_is_the_actual_connection_target(fetch_network):
    from app.crawlers.fetcher import FetchPolicy, SafeFetcher

    ip = '2606:4700:4700::1111'
    fetch_network.configure(dns={'news.test.invalid': [ip]})
    with SafeFetcher(FetchPolicy(allowed_hosts=('news.test.invalid',))) as fetcher:
        assert fetcher.fetch('https://news.test.invalid/news').body
    assert {e['ip'] for e in fetch_network.events() if e['kind'] == 'connect'} == {ip}


@pytest.mark.parametrize('field', ['max_seconds', 'min_interval'])
def test_oversized_policy_integer_is_rejected_without_numeric_overflow(field):
    from app.crawlers.fetcher import FetchPolicy

    with pytest.raises(ValueError, match='Invalid ' + field):
        FetchPolicy(allowed_hosts=('news.test.invalid',), **{field: 10 ** 500})
