"""Data shared with the standalone HTTP helper (no Flask/application imports)."""
from dataclasses import dataclass
import ipaddress
import math
import re
from urllib.parse import urlsplit, urlunsplit

from requests.utils import requote_uri
from requests.models import PreparedRequest


class Rejected(Exception):
    def __init__(self, code, retry_after=None):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)


def public_ip(value):
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        raise Rejected('unsafe_url') from None
    if (not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback
            or ip.is_link_local or ip.is_unspecified
            or (ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo
                or ip in ipaddress.ip_network('64:ff9b::/96')
                or ip in ipaddress.ip_network('64:ff9b:1::/48')))):
        raise Rejected('unsafe_url')
    return str(ip)


def hostname(value):
    if type(value) is not str or '%' in value or len(value) > 253:
        raise Rejected('unsafe_url')
    try:
        return public_ip(value)
    except Rejected:
        if ':' in value:
            raise
    try:
        value = value.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError:
        raise Rejected('unsafe_url') from None
    label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    if not re.fullmatch(label + r'(?:\.' + label + r')+', value) or value.rsplit('.', 1)[-1].isdigit():
        raise Rejected('unsafe_url')
    return value


def uri_text(value):
    return re.sub(r'%[0-9a-fA-F]{2}', lambda match: match[0].upper(), requote_uri(value))


def canonical_url(value, allowed_hosts):
    if (type(value) is not str or not value or len(value) > 1000
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == '\\' for c in value)):
        raise Rejected('unsafe_url')
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'https', 'http'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in {None, 443 if parsed.scheme == 'https' else 80}):
            raise Rejected('unsafe_url')
        host = hostname(parsed.hostname)
        if host not in allowed_hosts:
            raise Rejected('unsafe_url')
        authority = f'[{host}]' if ':' in host else host
        normalized = uri_text(urlunsplit((parsed.scheme, authority, parsed.path or '/', parsed.query, '')))
        prepared = PreparedRequest()
        prepared.prepare_url(normalized, None)  # Same dot-segment normalization as the actual client.
        normalized = uri_text(prepared.url)
        if len(normalized) > 1000:
            raise Rejected('unsafe_url')
        return normalized
    except (ValueError, UnicodeError):
        raise Rejected('unsafe_url') from None


@dataclass(frozen=True)
class FetchPolicy:
    allowed_hosts: tuple[str, ...]
    max_seconds: float = 60
    max_requests: int = 16
    max_redirects: int = 5
    max_wire_bytes: int = 2 * 1024 * 1024
    max_response_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 8 * 1024 * 1024
    max_total_wire_bytes: int = 8 * 1024 * 1024
    min_interval: float = 0.25

    def __post_init__(self):
        if type(self.allowed_hosts) not in {list, tuple} or not 1 <= len(self.allowed_hosts) <= 16:
            raise ValueError('Invalid allowed_hosts')
        try:
            object.__setattr__(self, 'allowed_hosts', tuple(sorted({hostname(h) for h in self.allowed_hosts})))
        except Rejected:
            raise ValueError('Invalid allowed_hosts') from None
        if (type(self.max_seconds) not in {int, float} or not 0 < self.max_seconds <= 180
                or not math.isfinite(self.max_seconds)):
            raise ValueError('Invalid max_seconds')
        for name, upper in {'max_requests': 16, 'max_redirects': 5, 'max_wire_bytes': 2 * 1024 * 1024,
                            'max_response_bytes': 2 * 1024 * 1024, 'max_total_bytes': 8 * 1024 * 1024,
                            'max_total_wire_bytes': 8 * 1024 * 1024}.items():
            value = getattr(self, name)
            if type(value) is not int or not (0 if name == 'max_redirects' else 1) <= value <= upper:
                raise ValueError('Invalid ' + name)
        if (type(self.min_interval) not in {int, float} or not 0 <= self.min_interval <= 60
                or not math.isfinite(self.min_interval)):
            raise ValueError('Invalid min_interval')
