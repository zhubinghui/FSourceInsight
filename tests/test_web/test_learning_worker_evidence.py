"""Retained web evidence can be consumed without worker-side file writes."""
import errno
import os
from pathlib import Path

from tests.test_web import test_crawl_learning as base
from tests.test_web.test_crawl_config import recipe_for

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


def test_learning_consumes_retained_web_files_through_readonly_file_access(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in evidence_dir.iterdir()}
    identity = evidence_dir.stat()
    opened, denied = [], []
    original = os.open
    def read_only(path, flags, *args, **kwargs):
        folder = kwargs.get('dir_fd')
        info = os.fstat(folder) if folder is not None else None
        in_evidence = ((info is not None and (info.st_dev, info.st_ino) == (identity.st_dev, identity.st_ino))
                       or (isinstance(path, (str, os.PathLike)) and Path(path).is_absolute()
                           and Path(path).is_relative_to(evidence_dir)))
        if in_evidence:
            opened.append(flags)
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                denied.append(True)
                raise OSError(errno.EROFS, 'synthetic read-only mount')
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', read_only)
    model.provider.reply = recipe_for(source)
    base.deliver(learning_io)
    assert base.state(client, started.location) == 'awaiting_validation'
    assert opened and not denied
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in evidence_dir.iterdir()} == before
    assert len(model.provider.calls) == 1
    assert client.get('/api/v1/news').json['total'] == 0
