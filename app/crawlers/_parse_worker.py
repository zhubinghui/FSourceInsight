"""Dedicated, network-disabled document parser; no application imports."""
import base64
import json
from pathlib import Path
import signal
import socket
import sys
import time


def blocked(*args, **kwargs):
    raise ValueError('invalid_article')


sys.dont_write_bytecode = True
socket.getaddrinfo = socket.create_connection = blocked
for method in ('connect', 'connect_ex', 'send', 'sendall', 'sendto'):
    setattr(socket.socket, method, blocked)


def main():
    try:
        command = json.loads(sys.stdin.buffer.read(1024 * 1024 + 1))
        remaining = command['deadline'] - time.monotonic()
        if remaining <= 0:
            raise ValueError('resource_limit')
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        sys.path.insert(0, str(Path(__file__).parent))
        from _extraction import detail_fields, list_records
        body = base64.b64decode(command['body'], validate=True)
        if len(body) > 512 * 1024:
            raise ValueError('resource_limit')
        if command['kind'] == 'list':
            value = list_records(body, command['rule'], rss=command['rss'])
        elif command['kind'] == 'detail':
            value = detail_fields(body, command['rule'], command['url'])
        else:
            raise ValueError('invalid_article')
        output = json.dumps({'value': value}, ensure_ascii=False).encode()
        if len(output) > 2 * 1024 * 1024:
            raise ValueError('resource_limit')
    except (ImportError, SyntaxError):
        output = json.dumps({'error': 'parser_unavailable'}).encode()
    except Exception as exc:
        code = str(exc) if isinstance(exc, ValueError) and str(exc) in {'resource_limit', 'low_quality', 'missing_fields', 'login_required', 'paywall', 'captcha'} else 'invalid_article'
        output = json.dumps({'error': code}).encode()
    sys.stdout.buffer.write(output)


if __name__ == '__main__':
    main()
