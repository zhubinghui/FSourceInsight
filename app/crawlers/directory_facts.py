"""Read address and organisation type from a member-directory detail page.

Facts are evidence for the reviewer, not approval. Any fetch or parse problem
yields no facts; there is no direct-HTTP fallback.
"""
import logging
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

logger = logging.getLogger(__name__)

_ENTITY_TYPES = [
    (('higher education', 'research centre', 'technology platform'), 'research_education'),
    (('economic development', 'bank', 'local authority', 'cluster'), 'ecosystem_support'),
    (('large corporation', 'mid-cap'), 'corporate'),
    (('sme', 'start-up', 'startup'), 'company'),
]


def parse_directory_facts(html: str) -> dict:
    soup = BeautifulSoup(html or '', 'lxml')
    for tag in soup(['script', 'style']):
        tag.decompose()
    text = ' '.join(soup.get_text(' ').split())
    address = re.search(r'Contact details Adress (.*?) (?:Contact |Website|News |#WeAre|$)', text)
    located = re.search(r"\b(\d{5})\s+([A-Za-zÀ-ÿ'’\- ]+?)(?:\s+CEDEX.*)?$", address.group(1)) if address else None
    if not located:
        return {}
    facts = {'postcode': located.group(1), 'city': located.group(2).strip().title()}
    org_type = re.search(r'Type of Organization (.*?) (?:Year founded|Themes)', text)
    if org_type:
        lowered = org_type.group(1).lower()
        facts['entity_type'] = next((entity for needles, entity in _ENTITY_TYPES
                                     if lowered.startswith(needles)), None)
        if facts['entity_type'] is None:
            del facts['entity_type']
    return facts


def fetch_directory_facts(url: str) -> dict:
    try:
        policy = FetchPolicy(allowed_hosts=(urlsplit(url).hostname,), max_seconds=15)
        with SafeFetcher(policy) as fetcher:
            response = fetcher.fetch(url)
    except (ValueError, FetchError) as exc:
        logger.info('directory facts unavailable: %s', getattr(exc, 'code', 'invalid_url'))
        return {}
    return parse_directory_facts(response.body)
