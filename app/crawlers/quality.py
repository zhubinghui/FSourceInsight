"""Deterministic cleaning and comparison; never model self-assessment."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from statistics import median
from zoneinfo import ZoneInfo
import re
from bs4 import BeautifulSoup


def text(value):
    return ' '.join(value.split())


def bounded_document(body):
    if len(body) > 512 * 1024:
        raise ValueError('resource_limit')
    soup = BeautifulSoup(body, 'lxml', from_encoding='utf-8')
    stack, count = [(soup, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > 64 or count > 20000:
            raise ValueError('resource_limit')
        stack.extend((child, depth + 1) for child in getattr(node, 'contents', ()))
    return soup


def clean_document(body, remove=()):
    soup = bounded_document(body)
    for selector, code in (('input[type="password"]', 'login_required'),
                           ('.paywall, #paywall, [data-paywall]', 'paywall'),
                           ('#challenge-form', 'captcha')):
        if soup.select_one(selector):
            raise ValueError(code)
    for node in soup.select('script,style,noscript,iframe,form,nav,footer,header,template,[hidden],[aria-hidden="true"]'):
        node.decompose()
    for node in soup.select('[style]'):
        if node.attrs is not None and re.search(r'(?:display:none|visibility:hidden)', re.sub(r'\s+', '', node.get('style', '')).casefold()):
            node.decompose()
    for selector in remove:
        for node in soup.select(selector):
            node.decompose()
    return soup


def read_fields(root, fields):
    values = {}
    for name, rule in fields.items():
        node = root.select_one(rule['selector'])
        if node is None:
            continue
        if rule['read'] == 'attr':
            value = node.get(rule['attr'])
            value = value if isinstance(value, str) else None
        elif rule['read'] == 'paragraphs':
            paragraphs = [text(n.get_text(' ', strip=True)) for n in node.select('p')]
            value = '\n\n'.join(p for p in paragraphs if p) or text(node.get_text(' ', strip=True))
        else:
            value = text(node.get_text(' ', strip=True))
        if value and value.strip():
            if len(value.encode()) > 65535 or sum(len(v.encode()) for v in values.values()) + len(value.encode()) > 1024 * 1024:
                raise ValueError('resource_limit')
            values[name] = value.strip()
    return values


def link_noise(node):
    total = len(node.get_text(' ', strip=True))
    links = sum(len(a.get_text(' ', strip=True)) for a in node.select('a'))
    return bool(total and links / total > 0.35)


def clean_content(value):
    if not re.search(r'<[a-zA-Z/!]', value):
        return '\n\n'.join(text(p) for p in value.split('\n\n') if p.strip())
    soup = clean_document(value.encode())
    if link_noise(soup):
        raise ValueError('low_quality')
    paragraphs = [text(p.get_text(' ', strip=True)) for p in soup.select('p')]
    return '\n\n'.join(p for p in paragraphs if p) or text(soup.get_text(' ', strip=True))


def body_matches(title, content):
    if not content:
        return False
    paragraphs = [text(p).casefold() for p in content.split('\n\n') if p.strip()]
    if not paragraphs or len(set(paragraphs)) / len(paragraphs) < 0.8:
        return False
    words = set(re.findall(r'\w+', title.casefold())) - {'the', 'and', 'with', 'for', 'les', 'des', 'une', 'dans', 'pour', 'sur', 'avec'}
    words = {w for w in words if len(w) > 2}
    cjk = re.findall(r'[\u3400-\u9fff]{2,}', title)
    words.update(w[i:i+2] for w in cjk for i in range(len(w)-1))
    return not words or any(word in content.casefold() for word in words)


def titles_match(first, second):
    tokens = lambda value: set(re.findall(r'\w+', value.casefold()))
    a, b = tokens(first), tokens(second)
    return bool(a and b) and len(a & b) / min(len(a), len(b)) >= 0.5


@dataclass(frozen=True)
class QualityProfile:
    min_content_chars: int = 200
    min_paragraphs: int = 2
    max_parse_seconds: float = 3
    recent_valid_counts: tuple[int, ...] = ()

    def __post_init__(self):
        if (type(self.recent_valid_counts) not in {list, tuple} or len(self.recent_valid_counts) > 30
                or any(type(n) is not int or not 0 <= n <= 200 for n in self.recent_valid_counts)):
            raise ValueError('Invalid quality profile')
        object.__setattr__(self, 'recent_valid_counts', tuple(self.recent_valid_counts))
        if type(self.max_parse_seconds) not in {int, float} or not 0 < self.max_parse_seconds <= 3:
            raise ValueError('Invalid quality profile')
        for name, limit in [('min_content_chars', 65535), ('min_paragraphs', 100)]:
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= limit:
                raise ValueError('Invalid quality profile')


def below_baseline(valid, discovered, profile):
    return ((discovered > 0 and valid / discovered < 0.9)
            or (len(profile.recent_valid_counts) >= 3 and valid < median(profile.recent_valid_counts) * 0.5))


def parse_date(value, zone):
    if not value:
        return None
    try:
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            date = parsedate_to_datetime(value)
        if date.utcoffset() is not None:
            return date.astimezone(timezone.utc)
        if not zone or not re.search(r'\d{2}:\d{2}', value):
            return None
        tz = ZoneInfo(zone)
        choices = set()
        for fold in (0, 1):
            candidate = date.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
            if candidate.astimezone(tz).replace(tzinfo=None) == date:
                choices.add(candidate)
        return choices.pop() if len(choices) == 1 else None
    except (ValueError, TypeError, OverflowError):
        return None


def content_level(content, profile):
    if not content:
        return 'metadata_only'
    return 'full' if len(content) >= profile.min_content_chars and len(content.split('\n\n')) >= profile.min_paragraphs else 'excerpt'
