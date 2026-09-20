"""Startup discovery: scan configurable URLs to find new Grenoble companies.

Extracts company names from portfolio/directory pages, creates Company
records with is_grenoble=True, and triggers AI analysis generation.
"""
import logging
import re
from datetime import datetime

from urllib.parse import urlsplit

from app.crawlers.fetcher import SafeFetcher, FetchPolicy
from bs4 import BeautifulSoup
from slugify import slugify

from celery_app import celery
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.company import Company
from app.models.startup_source import StartupSource
from app.crawlers.directory_facts import fetch_directory_facts

logger = logging.getLogger(__name__)

def _extract_companies_from_page(url: str) -> list[dict]:
    # The configured directory host only. No redirect host auto-approval or
    # direct HTTP fallback, and every pagination request shares these limits.
    policy = FetchPolicy(allowed_hosts=(urlsplit(url).hostname,), max_seconds=30,
                         max_requests=6, max_response_bytes=512 * 1024,
                         max_wire_bytes=512 * 1024, max_total_bytes=2 * 1024 * 1024,
                         max_total_wire_bytes=2 * 1024 * 1024)
    with SafeFetcher(policy) as fetcher:
        return _extract_pages(url, fetcher)


def _page(fetcher, url):
    response = fetcher.fetch(url)
    if response.observation.http_status != 200:
        raise ValueError('Directory page unavailable')
    return BeautifulSoup(response.body, 'lxml')


def _extract_pages(url, fetcher):
    """Extract company names and metadata from a startup portfolio/directory page.

    Uses multiple strategies and handles pagination:
    1. data-name attributes (Linksium/Craft CMS pattern)
    2. Directory links with pagination (Minalogic pattern)
    3. Company name + description in text blocks (CEA-Leti pattern)
    """
    companies = []
    seen = set()

    # Fetch page(s) — handle SharePoint-style pagination for CEA sites
    pages_to_parse = []
    soup = _page(fetcher, url)
    pages_to_parse.append(soup)

    # Check for SharePoint pagination (Voir aussi / Suivant links)
    # Extract all unique GUID pagination parameters from page links
    page_text = soup.get_text()
    if 'Suivant' in page_text:
        guid_params = set()
        for a in soup.select('a[href*="g_"]'):
            href = a.get('href', '')
            gm = re.search(r'(g_[a-f0-9_]+)=(\d+)', href)
            if gm:
                guid_params.add(gm.group(1))

        for param in sorted(guid_params)[:1]:
            for pg in range(1, 5):
                sep = '&' if '?' in url else '?'
                pg_url = f'{url}{sep}{param}={pg}'
                try:
                    pg_soup = _page(fetcher, pg_url)
                    pages_to_parse.append(pg_soup)
                    if 'Suivant' not in pg_soup.get_text():
                        break
                except Exception:
                    break

    # Strategy 1: data-name attributes (Craft CMS / Linksium)
    for ps in pages_to_parse:
        for item in ps.select('[data-name][data-description]'):
            name = item.get('data-name', '').strip()
            desc = item.get('data-description', '').strip()
            year = item.get('data-year', '').strip()
            link = item.get('data-link', '').strip()
            if not name or len(name) < 2 or name.lower() in seen:
                continue
            if name.lower() in ('calque 1',):
                continue
            seen.add(name.lower())
            website = f'https://{link}' if link and not link.startswith('http') else link
            companies.append({
                'name': name,
                'description': desc[:200] if desc else None,
                'website': website or None,
                'year': year or None,
            })

    # Strategy 2: Directory links with pagination (/page/N/)
    for ps in pages_to_parse:
        _extract_directory_links(ps, url, seen, companies)
    if 'member-directory' in url or 'annuaire' in url:
        base_url = url.rstrip('/')
        for page_num in range(2, 6):
            page_url = f'{base_url}/page/{page_num}/'
            try:
                ps = _page(fetcher, page_url)
                before = len(companies)
                _extract_directory_links(ps, url, seen, companies)
                if len(companies) == before:
                    break
            except Exception:
                break

    # Strategy 3: Text blocks with company names (CEA-Leti pattern).
    # Only a fallback: on pages with structured entries, free text is page chrome.
    if companies:
        return companies[:1000]
    noise = {
        'start-ups', 'suivant', 'programme', 'startup', 'contact',
        'direction', 'recherche', 'actualit', 'innover', 'navigation',
        'cea-leti', 'page', 'linkedin', 'you tube', 'videos', 'twitter',
        'facebook', 'instagram', 'technology research',
        'culture', 'institutionnel', 'recherche technologique',
        'naviguer', 'prisonnier', 'espaces', 'entre 2', 'acteur majeur',
        'que vous soyez', 'corps de texte',
        'voir aussi', 'documents', 'objectifs', 'highlights',
        'innovation days', 'appel a candidatures', 'hubup',
        'letidays', 'lemaire', 'axelle',
    }
    for ps in pages_to_parse:
        for seg in ps.get_text(separator='|||').split('|||'):
            seg = seg.strip()
            match = re.match(r'^([A-Za-z][A-Za-z0-9\-\' \.]{1,40})[,:]\s+(.{10,300})', seg)
            if match:
                name = match.group(1).strip()
                desc = match.group(2).strip()[:150]
                if name.lower() in seen:
                    continue
                if any(skip in name.lower() for skip in noise):
                    continue
                if not any(c.isalpha() for c in desc[:20]):
                    continue
                seen.add(name.lower())
                companies.append({
                    'name': name,
                    'description': desc,
                    'website': None,
                    'year': None,
                })

    return companies[:1000]


def _extract_directory_links(soup, base_url: str, seen: set, companies: list):
    """Extract company names from directory-style link lists."""
    skip_texts = {
        'home', 'contact', 'about', 'menu', 'search', 'back',
        'next', 'previous', 'page', 'filter', 'all', 'more',
        'news', 'event', 'login', 'members', 'directory',
        'members directory', 'member directory',
    }
    for a_tag in soup.select('a[href]'):
        href = a_tag.get('href', '')
        text = a_tag.get_text(strip=True)
        if not text or len(text) < 3 or len(text) > 80:
            continue
        if text.lower() in seen or text.lower() in skip_texts:
            continue
        # Skip pagination links
        if '/page/' in href:
            continue
        # Must look like a company detail link
        if any(kw in href.lower() for kw in [
            'member-directory/', 'startup/', 'portfolio/', '/company/',
            'annuaire/', 'nos-startups/',
        ]):
            # Skip links that are just the directory index
            if href.rstrip('/').endswith(('member-directory', 'annuaire', 'nos-startups')):
                continue
            seen.add(text.lower())
            full_url = href if href.startswith('http') else None
            companies.append({
                'name': text,
                'description': None,
                'website': full_url,
                'year': None,
            })


@celery.task(name='app.crawlers.startup_discovery.scan_startup_sources',
             queue='crawl')
def scan_startup_sources():
    """Read bounded directories; atomically save NEW companies and LLM intents."""
    from app.llm import budget, startup_analysis as jobs
    with Session(db.engine) as session:
        # Lab pages are not company directories, even if an old flag is active.
        sources = list(session.scalars(select(StartupSource).where(StartupSource.is_active.is_(True),
                                       StartupSource.source_type == 'startup')
                                       .order_by(StartupSource.last_scanned_at, StartupSource.id).limit(50)))
    total_new = 0
    for captured in sources:
        try:
            expected = jobs.source_input(captured)
            discovered = _extract_companies_from_page(captured.url)
            # Preparation is read-only; directory HTTP must never hold the
            # accounting mutex or flushed Company/job write locks.
            with Session(db.engine) as session:
                known = _known_aliases(session)
                prepared, seen = [], set()
                for entry in discovered:
                    name, slug = entry['name'], slugify(entry['name'])
                    if (not 2 <= len(name) <= 300 or not slug or len(slug) > 300
                            or name.lower() in known or slug in seen
                            or session.scalar(select(Company.id).where(Company.slug == slug).limit(1))):
                        continue
                    seen.add(slug)
                    prepared.append((entry, slug, jobs.website(entry.get('website'))))
                    if len(prepared) == 20:
                        break
            enriched = []
            for entry, slug, website in prepared:
                facts = {}
                if (website and 'member-directory/' in urlsplit(website).path
                        and urlsplit(website).hostname == urlsplit(captured.url).hostname):
                    facts = fetch_directory_facts(website)
                enriched.append((entry, slug, website, facts))
            pending = []
            with budget.transaction() as session:
                source = session.scalar(select(StartupSource).where(StartupSource.id == captured.id)
                                        .with_for_update().execution_options(populate_existing=True))
                if (source is None or jobs.source_input(source) != expected or not source.is_active
                        or source.source_type != 'startup'):
                    raise ValueError('Discovery source changed')
                known = _known_aliases(session)
                for entry, slug, website, facts in enriched:
                    name = entry['name']
                    if name.lower() in known or session.scalar(select(Company.id).where(Company.slug == slug).limit(1)):
                        continue
                    postcode = facts.get('postcode')
                    company = Company(name=name, slug=slug, description=entry.get('description'),
                                      website=website, is_grenoble=postcode is None or postcode.startswith('38'),
                                      postcode=postcode, city=facts.get('city'), entity_type=facts.get('entity_type'),
                                      company_stage='startup', is_auto_created=True, review_status='pending')
                    session.add(company)
                    pending.append(jobs.create(session, source, company))
                    if len(pending) >= 20:
                        break
                source.last_scanned_at = datetime.utcnow()
                source.companies_found = len(discovered)
            total_new += len(pending)
            for identity in pending:
                jobs.publish(identity)
        except Exception:
            # Independent context rollback prevents one broken directory from
            # committing its partial companies with the next source's result.
            logger.warning('Startup source %s scan unavailable; transaction outcome may require inspection', captured.id)
    return {'sources_scanned': len(sources), 'new_companies': total_new}


def _known_aliases(session):
    aliases = list(session.scalars(select(Company.aliases).where(Company.aliases.is_not(None)).limit(4097)))
    if len(aliases) > 4096 or any(row is not None and not isinstance(row, list) for row in aliases):
        raise ValueError('Discovery alias inventory unavailable')
    # SQL NULL and JSON null both mean no aliases, not a bad inventory.
    return {alias.lower() for row in aliases if row is not None for alias in row if isinstance(alias, str)}


# Sector inference from AI analysis text
_SECTOR_RULES = [
    ('Semiconductor', ['semiconductor', 'chip', 'wafer', 'mems', 'photonic', 'silicon', '芯片', '半导体', '晶圆', '硅基']),
    ('AI / Machine Learning', ['artificial intelligence', 'machine learning', 'deep learning', 'neural', 'ai ', ' ai', '人工智能', '机器学习', '深度学习', 'llm']),
    ('MedTech / Health', ['medical', 'health', 'diagnostic', 'pharma', 'biolog', 'surgery', 'implant', 'biotech', 'therapeut', '医疗', '诊断', '生物', '药']),
    ('Sensors / Photonics', ['sensor', 'lidar', 'infrared', 'optic', 'vision', 'camera', 'laser', 'display', 'oled', 'led', '传感', '激光', '光学']),
    ('Energy / CleanTech', ['energy', 'battery', 'solar', 'hydrogen', 'power', 'climat', 'recycl', 'green', '能源', '电池', '氢', '光伏', '回收']),
    ('IoT / Connected', ['iot', 'connected', 'rfid', 'smart city', 'wearable', '物联网', '智能', '可穿戴']),
    ('Quantum', ['quantum', 'qubit', '量子']),
    ('Software / Digital', ['software', 'saas', 'platform', 'digital', 'blockchain', 'cyber', 'algorithm', 'data analyt', '软件', '平台', '数据', '区块链']),
    ('Materials / Chemistry', ['material', 'chemistry', 'nano', 'coating', 'polymer', 'ceramic', '材料', '化学', '纳米', '涂层']),
    ('Robotics / Automation', ['robot', 'autonomous', 'drone', 'automation', '机器人', '自动化', '无人']),
]


def _infer_sector(analysis: dict) -> str | None:
    """Infer a sector from AI analysis overview + core_tech text."""
    text = ' '.join([
        analysis.get('overview', '') or '',
        analysis.get('core_tech', '') or '',
        analysis.get('business_status', '') or '',
    ]).lower()

    if not text.strip():
        return None

    best_sector = None
    best_score = 0
    for sector_name, keywords in _SECTOR_RULES:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_sector = sector_name

    return best_sector if best_score > 0 else None
