"""Supervised, run-scoped HTTP retrieval. No application credentials in the helper."""
import base64
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit

from ._fetch_policy import FetchPolicy, Rejected, canonical_url
from .contracts import CrawlError, FetchObservation

__all__ = ['FetchPolicy', 'FetchError', 'FetchResponse', 'SafeFetcher']


class FetchError(Exception):
    def __init__(self, code, retry_after=None):
        self.code, self.retry_after = code, retry_after
        self.error = CrawlError(stage='transport', code=code)
        self.retryable = self.error.retryable
        super().__init__(code)


@dataclass(frozen=True)
class FetchResponse:
    observation: FetchObservation
    body: bytes = field(repr=False)
    document_url: str = field(repr=False)  # Internal resolution only; never log/export wholesale.


class SafeFetcher:
    """One synchronous run; reuse within a context, never across runs or workers."""

    def __init__(self, policy: FetchPolicy):
        self._policy = policy
        self._deadline = time.monotonic() + policy.max_seconds
        self._process = None
        self._closed = False

    @property
    def policy(self):
        return self._policy

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self, *, force=False):
        self._closed = True
        if self._process is None:
            return
        process = self._process
        if force and process.poll() is None:
            process.kill()
        process.stdin.close()
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        finally:
            process.stdout.close()

    def fetch(self, url: str, *, transport='http') -> FetchResponse:
        if transport != 'http':
            raise FetchError('render_unavailable' if transport == 'browser' else 'unsafe_url')
        if self._closed:
            raise FetchError('fetch_closed')
        if time.monotonic() >= self._deadline:
            self.close(force=True)
            raise FetchError('timeout')
        try:
            url = canonical_url(url, self.policy.allowed_hosts)
        except Rejected as exc:
            raise FetchError(exc.code) from None
        try:
            reply = self._exchange({'url': url, 'policy': asdict(self.policy), 'deadline': self._deadline})
            if 'error' in reply:
                raise FetchError(reply['error'], reply.get('retry_after'))
            body = base64.b64decode(reply['body'], validate=True)
            observation = FetchObservation(
                requested_url=_observation_url(url), final_url=_observation_url(reply['url']), http_status=reply['status'],
                fetched_at=datetime.now(timezone.utc), content_type=reply['content_type'],
                response_bytes=len(body), snapshot_id=(None if reply['status'] == 304
                                                      else 'sha256:' + hashlib.sha256(body).hexdigest()),
            )
            return FetchResponse(observation, body, reply['url'])
        except FetchError:
            raise
        except (OSError, ValueError, KeyError):
            self.close(force=True)
            raise FetchError('network_error') from None

    def _exchange(self, command):
        if self._process is None:
            worker = Path(__file__).with_name('_fetch_worker.py')
            self._process = subprocess.Popen(
                [sys.executable, '-I', str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env={'PATH': os.defpath, 'LANG': 'C.UTF-8'}, close_fds=True,
            )
            os.set_blocking(self._process.stdin.fileno(), False)
            os.set_blocking(self._process.stdout.fileno(), False)
        message = json.dumps(command).encode() + b'\n'
        received = bytearray()
        position = 0
        with selectors.DefaultSelector() as selector:
            selector.register(self._process.stdin, selectors.EVENT_WRITE)
            selector.register(self._process.stdout, selectors.EVENT_READ)
            while True:
                remaining = self._deadline - time.monotonic()
                if remaining <= 0:
                    self.close(force=True)
                    raise FetchError('timeout')
                for key, mask in selector.select(remaining):
                    if mask & selectors.EVENT_WRITE:
                        position += os.write(key.fd, message[position:])
                        if position == len(message):
                            selector.unregister(key.fileobj)
                    else:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            expired = time.monotonic() >= self._deadline or self._process.poll() == -signal.SIGALRM
                            if expired:
                                self.close(force=True)
                                raise FetchError('timeout')
                            raise OSError('Helper closed')
                        received.extend(chunk)
                        if len(received) > 6 * 1024 * 1024:
                            self.close(force=True)
                            raise FetchError('too_large')
                        if received.endswith(b'\n'):
                            return json.loads(received)


def _observation_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
