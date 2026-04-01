"""Startup discovery: scan configurable URLs to find new Grenoble companies.

Extracts company names from portfolio/directory pages, creates Company
records with is_grenoble=True, and triggers AI analysis generation.
"""
import hashlib
import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from slugify import slugify

from celery_app import celery
from app.extensions import db
from app.models.company import Company
from app.models.startup_source import StartupSource

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.5',
}


def _extract_companies_from_page(url: str) -> list[dict]:
    """Extract company names and metadata from a startup portfolio/directory page.

    Uses multiple strategies:
    1. data-name attributes (Linksium pattern)
    2. Company name + description in text blocks (CEA-Leti pattern)
    3. Directory links with company names
    """
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')
    companies = []
    seen = set()

    # Strategy 1: data-name attributes (Craft CMS / Linksium)
    for item in soup.select('[data-name][data-description]'):
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

    # Strategy 2: Links to company detail pages in directories
    for a_tag in soup.select('a[href]'):
        href = a_tag.get('href', '')
        text = a_tag.get_text(strip=True)
        if not text or len(text) < 3 or len(text) > 60:
            continue
        if text.lower() in seen:
            continue
        # Skip navigation/generic links
        if any(skip in text.lower() for skip in [
            'home', 'contact', 'about', 'menu', 'search', 'back',
            'next', 'previous', 'page', 'filter', 'all', 'more',
            'news', 'event', 'login', 'member', 'directory',
        ]):
            continue
        # Must look like a company detail link
        if any(kw in href.lower() for kw in [
            'member-directory/', 'startup', 'portfolio', '/company/',
            'annuaire/', 'nos-startups/',
        ]):
            if text.lower() not in seen:
                seen.add(text.lower())
                full_url = href if href.startswith('http') else None
                companies.append({
                    'name': text,
                    'description': None,
                    'website': full_url,
                    'year': None,
                })

    # Strategy 3: Text blocks with company names (CEA-Leti pattern)
    for seg in soup.get_text(separator='|||').split('|||'):
        seg = seg.strip()
        match = re.match(r'^([A-Z][A-Za-z0-9\- ]{2,30}),\s+(.{10,200})', seg)
        if match:
            name = match.group(1).strip()
            desc = match.group(2).strip()[:150]
            if name.lower() in seen:
                continue
            if any(skip in name.lower() for skip in [
                'cea', 'leti', 'page', 'programme', 'contact', 'direction',
                'recherche', 'actualit', 'innover', 'navigation',
            ]):
                continue
            seen.add(name.lower())
            companies.append({
                'name': name,
                'description': desc,
                'website': None,
                'year': None,
            })

    return companies


@celery.task(name='app.crawlers.startup_discovery.scan_startup_sources',
             queue='crawl')
def scan_startup_sources():
    """Scan all active startup sources and discover new companies."""
    sources = StartupSource.query.filter_by(is_active=True).all()
    total_new = 0

    for source in sources:
        try:
            discovered = _extract_companies_from_page(source.url)
            new_count = 0

            for entry in discovered:
                name = entry['name']
                slug = slugify(name)

                # Skip if already exists
                existing = Company.query.filter_by(slug=slug).first()
                if existing:
                    continue

                # Also check aliases
                name_lower = name.lower()
                alias_match = False
                for c in Company.query.filter(Company.aliases.isnot(None)).all():
                    if c.aliases and name_lower in [a.lower() for a in c.aliases]:
                        alias_match = True
                        break
                if alias_match:
                    continue

                # Create new company
                company = Company(
                    name=name,
                    slug=slug,
                    description=entry.get('description'),
                    website=entry.get('website'),
                    is_grenoble=True,
                    company_stage='startup',
                    is_auto_created=True,
                )
                db.session.add(company)
                db.session.flush()
                new_count += 1
                logger.info(f'Discovered new startup: {name} (from {source.name})')

            source.last_scanned_at = datetime.utcnow()
            source.companies_found = len(discovered)
            db.session.commit()

            if new_count > 0:
                total_new += new_count
                logger.info(f'{source.name}: {len(discovered)} found, {new_count} new')

                # Trigger AI analysis for new companies
                _generate_analyses_for_new(source)
            else:
                logger.info(f'{source.name}: {len(discovered)} found, 0 new')

        except Exception as e:
            logger.warning(f'Startup scan failed for {source.name}: {e}')

    return {'sources_scanned': len(sources), 'new_companies': total_new}


def _generate_analyses_for_new(source: StartupSource):
    """Generate AI analysis for recently discovered companies from this source."""
    from app.llm.client import LLMClient

    new_companies = (
        Company.query
        .filter_by(is_grenoble=True, is_auto_created=True)
        .filter(Company.ai_analysis.is_(None))
        .order_by(Company.created_at.desc())
        .limit(10)
        .all()
    )

    if not new_companies:
        return

    try:
        client = LLMClient()
        for company in new_companies:
            analysis = client.analyze_company(
                name=company.name,
                sector=company.sector,
                headquarters=company.headquarters or 'Grenoble',
                description=company.description,
                spinoff_origin=company.spinoff_origin,
                company_stage=company.company_stage,
                recent_news='',
            )
            if isinstance(analysis, dict):
                company.ai_analysis = analysis
                company.ai_analysis_at = datetime.utcnow()
                # Sync website from AI if company doesn't have one
                if not company.website and analysis.get('website'):
                    company.website = analysis['website']
                db.session.commit()
                logger.info(f'AI analysis generated for {company.name}')
    except Exception as e:
        logger.warning(f'AI analysis generation failed: {e}')
