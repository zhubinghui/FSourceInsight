"""Child bootstrap: real HTTP implementation, synthetic DNS/socket/TLS only."""
import atexit
import base64
import io
import ipaddress
import json
import os
from pathlib import Path
import runpy
import socket
import ssl
import sys
import time
import tracemalloc

worker, scenario_path, trace_path = sys.argv[1:]
scenario = json.loads(Path(scenario_path).read_text())
dns_calls = {}
if scenario.get('legacy_adapter'):
    import requests.adapters
    delattr(requests.adapters.HTTPAdapter, 'get_connection_with_tls_context')


def record(**event):
    with open(trace_path, 'a') as log:
        log.write(json.dumps(event) + '\n')


def resolve(host, port, *args, **kwargs):
    if scenario.get('measure_memory') and not tracemalloc.is_tracing():
        tracemalloc.start()
    record(kind='dns', host=host)
    if scenario.get('dns_delays'):
        time.sleep(scenario['dns_delays'].pop(0))
    if scenario.get('dns_delay'):
        time.sleep(scenario['dns_delay'])
    addresses = scenario.get('dns', {}).get(host, ['93.184.216.34'])
    if addresses and isinstance(addresses[0], list):
        index = dns_calls.get(host, 0)
        dns_calls[host] = index + 1
        addresses = addresses[min(index, len(addresses) - 1)]
    return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM, 6, '',
             (ip, port)) for ip in addresses]


class FakeSocket:
    def __init__(self, family=socket.AF_INET, *args, **kwargs):
        self.family = family
        self.request = b''
        self.tls_host = None
        self.timeout = None
        self.closed = False
        self.r, self.w = os.pipe()

    def bind(self, address):
        raise OSError('No real network in fixture')

    def connect(self, address):
        self.address = address
        record(kind='connect', ip=address[0], port=address[1])

    def connect_ex(self, address):
        self.connect(address)
        return 0

    def getpeername(self):
        return (scenario.get('peer_ip', self.address[0]), self.address[1])

    def settimeout(self, timeout):
        self.timeout = timeout

    def gettimeout(self):
        return self.timeout

    def setsockopt(self, *args):
        pass

    def fileno(self):
        return self.r

    def sendall(self, data):
        self.request += bytes(data)

    def makefile(self, *args, **kwargs):
        text = self.request.decode('latin-1')
        self.request = b''
        lines = text.split('\r\n')
        headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
        path = lines[0].split(' ')[1]
        host = headers.get('Host', '')
        url = ('https' if self.tls_host else 'http') + '://' + host + path
        record(kind='http', url=url, headers=headers, at=time.monotonic())
        default = {'status': 404, 'body': ''} if path == '/robots.txt' else {'body': '<p>Bonjour</p>'}
        spec = scenario.get('routes', {}).get(url, default)
        body = base64.b64decode(spec['body_b64']) if 'body_b64' in spec else spec.get('body', '').encode()
        response_headers = {'Content-Type': 'text/plain' if path == '/robots.txt' else 'text/html'}
        if not spec.get('no_length'):
            response_headers['Content-Length'] = str(len(body))
        response_headers.update(spec.get('headers', {}))
        wire = f'HTTP/1.1 {spec.get("status", 200)} Synthetic\r\n'.encode()
        wire += ''.join(f'{key}: {value}\r\n' for key, value in response_headers.items()).encode()
        wire += b'\r\n' + body
        if spec.get('delay'):
            time.sleep(spec['delay'])
        class WireFile(io.BytesIO):
            def read(self, *args):
                if spec.get('body_timeout'):
                    raise TimeoutError('Synthetic read timeout')
                if spec.get('body_delay'):
                    time.sleep(spec['body_delay'])
                return super().read(*args)

        return WireFile(wire)

    def getpeercert(self, binary_form=False):
        host = scenario.get('cert_host', self.tls_host)
        try:
            ipaddress.ip_address(host)
            kind = 'IP Address'
        except ValueError:
            kind = 'DNS'
        return {'subjectAltName': [(kind, host)]}

    def close(self):
        if not self.closed:
            self.closed = True
            os.close(self.r)
            os.close(self.w)
            record(kind='close')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def wrap(context, sock, *args, **kwargs):
    sock.tls_host = kwargs['server_hostname']
    record(kind='tls', hostname=sock.tls_host, verify_mode=int(context.verify_mode))
    return sock


def memory_report():
    if tracemalloc.is_tracing():
        record(kind='memory', peak=tracemalloc.get_traced_memory()[1])


atexit.register(memory_report)
record(kind='environment', keys=sorted(os.environ))
socket.getaddrinfo = resolve
socket.socket = FakeSocket
socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Use numeric socket connect'))
ssl.SSLContext.wrap_socket = wrap
# -I avoids ambient import paths; only explicitly add the trusted worker directory.
sys.path.insert(0, str(Path(worker).parent))
runpy.run_path(worker, run_name='__main__')
