"""Private, opt-in raw evidence. References confer no fetch or approval authority."""
import base64
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
import hashlib
import fcntl
import json
import os
from pathlib import Path
import stat
import re
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

from ._fetch_policy import canonical_url, Rejected

TTL = 24 * 60 * 60
MAX_BUNDLE = 3 * 1024 * 1024
MAX_FILES = 32
MAX_TOTAL = 64 * 1024 * 1024
_KEY = re.compile(r'[0-9a-f]{32}\.json')


def binding(source_id, version_id, generation, source_hash, recipe_hash, engine, policy, quality, capture_id):
    return {'source_id': source_id, 'version_id': version_id, 'generation': generation, 'capture_id': capture_id,
            'source_fingerprint': source_hash, 'recipe_hash': recipe_hash, 'engine': engine,
            'fetch_policy': asdict(policy), 'quality_profile': asdict(quality)}


@contextmanager
def root(directory):
    if not isinstance(directory, str) or not Path(directory).is_absolute():
        raise ValueError('Evidence storage unavailable')
    path = Path(directory)
    # lstat rejects final symlinks before resolve can raise a path-bearing loop error.
    if stat.S_ISLNK(os.lstat(path).st_mode) or path.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('Evidence storage unavailable')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
            raise ValueError('Evidence storage unavailable')
        yield fd
    finally:
        os.close(fd)


def _private_file(info):
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid() or info.st_nlink != 1):
        raise ValueError('Evidence storage unavailable')


@contextmanager
def _locked(directory):
    with root(directory) as folder:
        fd = os.open('.evidence.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=folder)
        try:
            _private_file(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield folder
        finally:
            os.close(fd)


def _inventory(folder):
    files = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name == '.evidence.lock':
                continue
            if not _KEY.fullmatch(entry.name) or len(files) >= MAX_FILES:
                raise ValueError('Evidence storage unavailable')
            info = entry.stat(follow_symlinks=False)
            _private_file(info)
            files.append((entry.name, info.st_size, info.st_mtime))
    return files


def _prune(folder, files):
    expired = [name for name, _, modified in files if modified + TTL <= time.time()]
    for name in expired:
        os.unlink(name, dir_fd=folder)
    if expired:
        os.fsync(folder)
    return len(expired)


def cleanup(directory):
    with _locked(directory) as folder:
        return _prune(folder, _inventory(folder))


def save(directory, pages, inputs):
    if (not 1 <= len(pages) <= 6 or sum(len(p.response.body) for p in pages) > 2 * 1024 * 1024
            or any(len(p.response.body) > 512 * 1024 for p in pages)):
        raise ValueError('Evidence size unavailable')
    values = []
    for page in pages:
        observation = asdict(page.response.observation)
        observation['fetched_at'] = page.response.observation.fetched_at.isoformat()
        values.append({'url': page.url, 'document_url': page.response.document_url,
                       'observation': observation, 'body': base64.b64encode(page.response.body).decode()})
    expires = int(time.time()) + TTL
    key = uuid.uuid4().hex + '.json'
    data = json.dumps({'format': 1, 'key': key, 'expires_at': expires, 'inputs': inputs,
                       'pages': values}, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > MAX_BUNDLE:
        raise ValueError('Evidence size unavailable')
    with _locked(directory) as folder:
        files = _inventory(folder)
        if _prune(folder, files):
            files = _inventory(folder)
        if len(files) >= MAX_FILES or sum(size for _, size, _ in files) + len(data) > MAX_TOTAL:
            raise ValueError('Evidence capacity unavailable')
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(folder)
    return {'key': key, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'expires_at': expires}


def _reference(reference):
    if (type(reference) is not dict or set(reference) != {'key', 'sha256', 'size', 'expires_at'}
            or type(reference['key']) is not str or not _KEY.fullmatch(reference['key'])
            or type(reference['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', reference['sha256'])
            or type(reference['size']) is not int or not 0 < reference['size'] <= MAX_BUNDLE
            or type(reference['expires_at']) is not int):
        raise ValueError('Evidence unavailable')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Evidence unavailable')
        result[key] = value
    return result


def _no_constant(value):
    raise ValueError('Evidence unavailable')


def _page_valid(page, hosts):
    obs, body = page.response.observation, page.response.body
    try:
        if canonical_url(page.url, hosts) != page.url or canonical_url(page.response.document_url, hosts) != page.response.document_url:
            return False
    except Rejected:
        return False
    start, end = urlsplit(page.url), urlsplit(page.response.document_url)
    return (obs.status == 'ok' and obs.response_bytes == len(body)
            and obs.snapshot_id == 'sha256:' + hashlib.sha256(body).hexdigest()
            and obs.requested_url == urlunsplit((start.scheme, start.netloc, start.path, '', ''))
            and obs.final_url == urlunsplit((end.scheme, end.netloc, end.path, '', '')))


def load(directory, reference, inputs):
    from .contracts import FetchObservation
    from .engine import PageSnapshot
    from .fetcher import FetchResponse

    _reference(reference)
    if reference['expires_at'] <= time.time():
        raise ValueError('Evidence unavailable')
    with root(directory) as folder:
        fd = os.open(reference['key'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            _private_file(info)
            if not 0 < info.st_size <= MAX_BUNDLE:
                raise ValueError('Evidence unavailable')
            data = stream.read(MAX_BUNDLE + 1)
    if len(data) != reference['size'] or hashlib.sha256(data).hexdigest() != reference['sha256']:
        raise ValueError('Evidence unavailable')
    doc = json.loads(data, object_pairs_hook=_object, parse_constant=_no_constant)
    if type(doc) is not dict or set(doc) != {'format', 'key', 'expires_at', 'inputs', 'pages'} or type(doc['format']) is not int:
        raise ValueError('Evidence unavailable')
    # Compare JSON forms so frozen tuple policy fields survive their DB JSON round trip.
    if (doc['format'] != 1 or doc['key'] != reference['key'] or doc['expires_at'] != reference['expires_at']
            or doc['inputs'] != json.loads(json.dumps(inputs))):
        raise ValueError('Evidence unavailable')
    if type(doc['pages']) is not list or not 1 <= len(doc['pages']) <= 6:
        raise ValueError('Evidence unavailable')
    pages = []
    for page in doc['pages']:
        if type(page) is not dict or set(page) != {'url', 'document_url', 'observation', 'body'}:
            raise ValueError('Evidence unavailable')
        obs = dict(page['observation'])
        obs['fetched_at'] = datetime.fromisoformat(obs['fetched_at'])
        if obs['error'] is not None:
            raise ValueError('Evidence unavailable')
        pages.append(PageSnapshot(page['url'], FetchResponse(
            observation=FetchObservation(**obs), body=base64.b64decode(page['body'], validate=True),
            document_url=page['document_url'])))
    if (sum(len(p.response.body) for p in pages) > 2 * 1024 * 1024
            or any(len(p.response.body) > 512 * 1024 or not _page_valid(p, inputs['fetch_policy']['allowed_hosts']) for p in pages)
            or len({p.url for p in pages}) != len(pages) or reference['expires_at'] <= time.time()):
        raise ValueError('Evidence unavailable')
    return tuple(pages)


def inspect(directory, reference, inputs):
    if not reference:
        return 'not_retained'
    try:
        _reference(reference)
        if reference['expires_at'] <= time.time():
            return 'expired'
        load(directory, reference, inputs)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return 'unavailable'
    return 'available'
