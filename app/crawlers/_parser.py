"""Supervise parsing separately from HTTP; only structured bounded data crosses exec."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def parse(body, rule, *, kind, deadline, rss=False, url=None):
    remaining = deadline - time.monotonic()
    if remaining <= 0 or len(body) > 512 * 1024:
        raise ValueError('resource_limit')
    command = {'body': base64.b64encode(body).decode(), 'rule': rule, 'kind': kind,
               'rss': rss, 'url': url, 'deadline': deadline}
    try:
        process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('_parse_worker.py'))],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env={'PATH': os.defpath, 'LANG': 'C.UTF-8'}, close_fds=True)
    except OSError:
        raise ValueError('parser_unavailable') from None
    with process:
        try:
            output, _ = process.communicate(json.dumps(command).encode(), timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=1)
            raise ValueError('resource_limit') from None
        if process.returncode != 0 or len(output) > 2 * 1024 * 1024:
            raise ValueError('resource_limit')
    try:
        result = json.loads(output)
    except ValueError:
        raise ValueError('invalid_article') from None
    if 'error' in result:
        raise ValueError(result['error'])
    return result['value']
