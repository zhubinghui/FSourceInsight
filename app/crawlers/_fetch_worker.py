"""Standalone HTTP process, stdin/stdout JSON protocol; no app imports or secrets.

Only the supervising SafeFetcher launches this script. The process can be killed
at its absolute deadline even while libc DNS or HTTP headers are blocked.
"""
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import ipaddress
import http.client
import json
import re
import signal
import socket
import sys
import time
import zlib
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import TimeoutError as HTTPTimeout
from urllib3.exceptions import SSLError as HTTPTLSError

sys.path.insert(0, str(Path(__file__).parent))
from _fetch_policy import Rejected, canonical_url, public_ip
from _fetch_robots import RobotsRules
from _fetch_io import ProtocolBudget, ResponseSocket

# These parser limits are process-local, not changes to Flask/LLM HTTP clients.
http.client._MAXLINE = 8192
http.client._MAXHEADERS = 64


class NumericConnection:
    def __init__(self, *args, protocol_budget, **kwargs):
        self.protocol_budget = protocol_budget
        super().__init__(*args, **kwargs)

    def response_class(self, sock, *args, **kwargs):
        return http.client.HTTPResponse(ResponseSocket(sock, self.protocol_budget), *args, **kwargs)

    def _new_conn(self):
        address = ipaddress.ip_address(self.host)
        sock = socket.socket(socket.AF_INET6 if address.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect((str(address), self.port))
            if ipaddress.ip_address(sock.getpeername()[0]) != address:
                raise Rejected('unsafe_url')
            return sock
        except BaseException:
            sock.close()
            raise


class NumericHTTPConnection(NumericConnection, HTTPConnection):
    pass


class NumericHTTPSConnection(NumericConnection, HTTPSConnection):
    pass


class NumericHTTPPool(HTTPConnectionPool):
    ConnectionCls = NumericHTTPConnection


class NumericHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = NumericHTTPSConnection


class PinnedAdapter(HTTPAdapter):
    def __init__(self, protocol_budget):
        super().__init__(max_retries=0)
        self.protocol_budget = protocol_budget
        self.pools = {}
        self.address = None

    def get_connection(self, *args, **kwargs):
        # A legacy client must not silently fall back to an unpinned default pool.
        raise Rejected('transport_unavailable')

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        parsed = urlsplit(request.url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        key = (parsed.scheme, parsed.hostname, port, self.address)
        if key not in self.pools:
            if parsed.scheme == 'https':
                self.pools[key] = NumericHTTPSPool(self.address, port, maxsize=1,
                                                  server_hostname=parsed.hostname,
                                                  assert_hostname=parsed.hostname,
                                                  protocol_budget=self.protocol_budget)
            else:
                self.pools[key] = NumericHTTPPool(self.address, port, maxsize=1,
                                                 protocol_budget=self.protocol_budget)
        return self.pools[key]

    def close(self):
        for pool in self.pools.values():
            pool.close()
        super().close()


class ControlledSession(requests.Session):
    def resolve_redirects(self, *args, **kwargs):
        # Requests otherwise consumes redirect bodies to build Response.next,
        # even with allow_redirects=False and stream=True.
        return iter(())


class Engine:
    def __init__(self, policy, deadline):
        if not hasattr(HTTPAdapter, 'get_connection_with_tls_context'):
            raise Rejected('transport_unavailable')
        self.policy, self.deadline = policy, deadline
        self.session = ControlledSession()
        self.session.trust_env = False
        self.session.headers = {'User-Agent': 'FSourceInsightBot/1.0', 'Accept-Encoding': 'identity'}
        self.protocol_budget = ProtocolBudget(policy)
        self.adapter = PinnedAdapter(self.protocol_budget)
        self.session.mount('http://', self.adapter)
        self.session.mount('https://', self.adapter)
        self.robots = {}
        self.requests_used = self.wire_used = self.decoded_used = 0
        self.last_request = {}
        self.cooldowns = {}
        self.robot_delays = {}

    def request(self, url):
        url = canonical_url(url, self.policy['allowed_hosts'])
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        until, code = self.cooldowns.get(parsed.hostname, (0, 'rate_limited'))
        if until > time.monotonic():
            raise Rejected(code, math.ceil(until - time.monotonic()))
        if (self.requests_used >= self.policy['max_requests']
                or self.wire_used >= self.policy['max_total_wire_bytes']
                or self.decoded_used >= self.policy['max_total_bytes']
                or self.protocol_budget.used >= self.protocol_budget.total):
            raise Rejected('budget_exceeded')
        interval = max(self.policy['min_interval'], self.robot_delays.get(parsed.hostname, 0))
        delay = interval - (time.monotonic() - self.last_request.get(parsed.hostname, 0))
        if delay > 0:
            time.sleep(delay)
        if time.monotonic() >= self.deadline:
            raise Rejected('timeout')
        self.requests_used += 1
        self.last_request[parsed.hostname] = time.monotonic()
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        approved = [public_ip(record[4][0]) for record in addresses]
        if not approved:
            raise Rejected('network_error')
        self.adapter.address = approved[0]
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Rejected('timeout')
        self.session.cookies.clear()
        response = self.session.get(url, headers={'Host': parsed.netloc}, allow_redirects=False,
                                    timeout=min(10, remaining), stream=True)
        self.last_request[parsed.hostname] = time.monotonic()
        if sum(len(k) + len(v) + 4 for k, v in response.headers.items()) > 65536:
            response.close()
            raise Rejected('too_large')
        return response

    def fetch(self, url):
        return self.follow(url)

    def follow(self, url, *, robots=False):
        seen = set()
        while True:
            url = canonical_url(url, self.policy['allowed_hosts'])
            if url in seen or len(seen) > self.policy['max_redirects']:
                raise Rejected('redirect_limit')
            seen.add(url)
            parsed = urlsplit(url)
            origin = f'{parsed.scheme}://{parsed.netloc}'
            if not robots:
                if origin not in self.robots:
                    result = self.follow(origin + '/robots.txt', robots=True)
                    rules = RobotsRules(base64.b64decode(result['body']) if result else b'')
                    self.robots[origin] = rules
                    self.robot_delays[parsed.hostname] = max(self.robot_delays.get(parsed.hostname, 0), rules.delay)
                if not self.robots[origin].allows(url):
                    raise Rejected('robots_denied')
            with self.request(url) as response:
                status = response.status_code
                if status in {301, 302, 303, 307, 308}:
                    target = canonical_url(urljoin(url, response.headers.get('Location', '')),
                                           self.policy['allowed_hosts'])
                    if parsed.scheme == 'https' and urlsplit(target).scheme != 'https':
                        raise Rejected('unsafe_url')
                    url = target
                    continue
                if robots and status in {404, 410}:
                    return None
                if robots and status == 304:
                    raise Rejected('robots_unavailable')
                if status in {401, 403}:
                    raise Rejected('robots_denied' if robots else 'forbidden')
                if status == 429 or status >= 500:
                    code = 'rate_limited' if status == 429 else 'server_error'
                    hint = response.headers.get('Retry-After', '')
                    seconds = None
                    if hint.isascii() and hint.isdigit():
                        seconds = min(int(hint), 86400) if len(hint) <= 6 else 86400
                    elif hint:
                        try:
                            date = parsedate_to_datetime(hint)
                            seconds = min(86400, max(0, math.ceil((date - datetime.now(timezone.utc)).total_seconds())))
                        except (ValueError, TypeError, OverflowError):
                            pass
                    if seconds:
                        self.cooldowns[parsed.hostname] = (time.monotonic() + seconds, code)
                    raise Rejected(code, seconds)
                if not 200 <= status < 300 and status != 304:
                    raise Rejected('http_error')
                content_type = response.headers.get('Content-Type', '')
                token = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
                mime_pattern = rf'{token}/{token}(?:[ \t]*;[ \t]*{token}=(?:{token}|"[^"\\\\\x00-\x1f\x7f-\xff]*"))*[ \t]*'
                if content_type and not re.fullmatch(mime_pattern, content_type):
                    raise Rejected('unsupported_content_type')
                media = content_type.split(';')[0].strip().lower()
                allowed = {'text/html', 'application/xhtml+xml', 'text/plain', 'application/xml',
                           'text/xml', 'application/rss+xml', 'application/atom+xml',
                           'application/json', 'application/ld+json'}
                if status not in {204, 304} and (media not in allowed or (robots and media != 'text/plain')):
                    raise Rejected('unsupported_content_type')
                body = b'' if status == 304 else self.read_body(response, robots=robots)
                return {'url': url, 'status': status, 'body': base64.b64encode(body).decode(),
                        'content_type': media or None}

    def read_body(self, response, *, robots=False):
        limit = min(self.policy['max_response_bytes'], 512 * 1024 if robots else 2 * 1024 * 1024)
        wire_limit = min(self.policy['max_wire_bytes'], self.policy['max_total_wire_bytes'] - self.wire_used)
        length = response.headers.get('Content-Length')
        if length is not None:
            if not re.fullmatch(r'[0-9]{1,12}', length) or 'Transfer-Encoding' in response.headers:
                raise Rejected('http_error')
            if int(length) > wire_limit:
                raise Rejected('too_large')
        encoding = response.headers.get('Content-Encoding', 'identity').strip().lower()
        if encoding not in {'identity', 'gzip'}:
            raise Rejected('decode_error')
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == 'gzip' else None
        body = bytearray()
        wire = 0
        while True:
            if time.monotonic() >= self.deadline:
                raise Rejected('timeout')
            chunk = response.raw.read(min(16384, max(1, wire_limit - wire + 1)), decode_content=False)
            if not chunk:
                break
            wire += len(chunk)
            self.wire_used += len(chunk)
            if wire > wire_limit:
                raise Rejected('too_large')
            room = min(limit - len(body), self.policy['max_total_bytes'] - self.decoded_used)
            decoded = decoder.decompress(chunk, max(1, room + 1)) if decoder else chunk
            self.decoded_used += len(decoded)
            if len(decoded) > room:
                raise Rejected('too_large')
            body.extend(decoded)
            if decoder and (decoder.unused_data or decoder.unconsumed_tail):
                raise Rejected('decode_error')
        if decoder and not decoder.eof:
            raise Rejected('decode_error')
        return bytes(body)


def main():
    engine = None
    try:
        while line := sys.stdin.buffer.readline(65537):
            try:
                command = json.loads(line)
                if engine is None:
                    remaining = command['deadline'] - time.monotonic()
                    if remaining <= 0:
                        raise Rejected('timeout')
                    # Default SIGALRM terminates in the kernel, even during blocking DNS.
                    # This is a dedicated helper; never install this on a business worker.
                    signal.signal(signal.SIGALRM, signal.SIG_DFL)
                    signal.setitimer(signal.ITIMER_REAL, remaining)
                    engine = Engine(command['policy'], command['deadline'])
                result = engine.fetch(command['url'])
            except Rejected as exc:
                result = {'error': exc.code, 'retry_after': exc.retry_after}
            except zlib.error:
                result = {'error': 'decode_error'}
            except (requests.exceptions.SSLError, HTTPTLSError):
                result = {'error': 'tls_error'}
            except (requests.Timeout, HTTPTimeout):
                result = {'error': 'timeout'}
            except Exception:
                result = {'error': 'network_error'}
            sys.stdout.write(json.dumps(result) + '\n')
            sys.stdout.flush()
    finally:
        if engine:
            engine.session.close()


if __name__ == '__main__':
    main()
