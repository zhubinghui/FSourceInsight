"""Bounded robots rules for the standalone worker, never network fetching."""
from fnmatch import fnmatchcase
import math
import re
from urllib.parse import urlsplit, unquote_to_bytes

from _fetch_policy import Rejected, uri_text

BOT = 'FSourceInsightBot'


class RobotsRules:
    def __init__(self, body=b''):
        try:
            text = body.decode('utf-8-sig')
        except UnicodeError:
            raise Rejected('robots_unavailable') from None
        if '<' in text or len(text.splitlines()) > 2048:
            raise Rejected('robots_unavailable')
        groups = []
        agents, rules, delays = [], [], []
        has_directives = False
        for raw in text.splitlines():
            if len(raw) > 2048:
                raise Rejected('robots_unavailable')
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            if ':' not in line:
                raise Rejected('robots_unavailable')
            key, value = (part.strip() for part in line.split(':', 1))
            key = key.lower()
            if not re.fullmatch('[a-z][a-z-]*', key):
                raise Rejected('robots_unavailable')
            if key == 'user-agent':
                if has_directives:
                    groups.append((agents, rules, delays))
                    agents, rules, delays, has_directives = [], [], [], False
                agents.append(value.lower())
            elif key in {'allow', 'disallow', 'crawl-delay'}:
                if not agents:
                    raise Rejected('robots_unavailable')
                has_directives = True
                if key == 'crawl-delay':
                    try:
                        delay = float(value)
                        if not math.isfinite(delay) or delay < 0:
                            raise ValueError()
                        delays.append(delay)
                    except ValueError:
                        raise Rejected('robots_unavailable') from None
                elif value:
                    if not value.startswith('/'):
                        raise Rejected('robots_unavailable')
                    rules.append((uri_text(value), key == 'allow'))
            elif not agents and key != 'sitemap':
                raise Rejected('robots_unavailable')
        groups.append((agents, rules, delays))
        specific = [g for g in groups if BOT.lower() in g[0]]
        selected = specific or [g for g in groups if '*' in g[0]]
        self.rules = [rule for _, rules, _ in selected for rule in rules]
        self.delay = max([d for _, _, delays in selected for d in delays] or [0])

    def allows(self, url):
        parts = urlsplit(url)
        path = uri_text(parts.path + ('?' + parts.query if parts.query else ''))
        matches = []
        for rule, allow in self.rules:
            exact = rule.endswith('$')
            raw = rule[:-1] if exact else rule
            # robots recognizes '*' only. Treat fnmatch's '?'/'[' as literals.
            pattern = raw.replace('[', '[[]').replace('?', '[?]') + ('' if exact else '*')
            if fnmatchcase(path, pattern):
                matches.append((len(unquote_to_bytes(raw.replace('*', ''))), allow))
        return max(matches)[1] if matches else True  # equal specificity: Allow wins
