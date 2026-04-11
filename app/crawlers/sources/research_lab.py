"""Generic research lab crawler — scrapes news, publications, and events pages.

Works for labs without RSS feeds by crawling their news/actualites/publications
pages and extracting article links. Registered for multiple lab slugs.
"""
import hashlib
import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.5',
}

# Map each lab slug to its news/publications pages
LAB_PAGES = {
    'lig-lab': [
        'https://www.liglab.fr/fr/presentation/toute-lactualite',
        'https://www.liglab.fr/fr/produits-recherche/publications',
    ],
    'gipsa-lab': [
        'https://www.gipsa-lab.grenoble-inp.fr/',
        'https://www.gipsa-lab.grenoble-inp.fr/les-publications',
    ],
    'tima-lab': [
        'https://tima.univ-grenoble-alpes.fr/laboratory/news',
        'https://tima.univ-grenoble-alpes.fr/outreach/publications',
    ],
    'verimag': [
        'https://www-verimag.imag.fr/Historique-des-faits-marquants.html?lang=fr',
        'https://www-verimag.imag.fr/Publications.html?lang=fr',
    ],
    'grenoblealpes': [
        'https://www.grenoblealpesmetropole.fr/45-nos-actualites.htm',
        'https://www.grenoblealpesmetropole.fr/938-l-actualite-pour-les-pros.htm',
        'https://www.grenoblealpesmetropole.fr/915-l-agenda-de-la-metropole.htm',
    ],
}


class ResearchLabCrawler(BaseCrawler):
    """Generic crawler for Grenoble research lab websites."""

    def __init__(self, source: NewsSource):
        super().__init__(source)
        self.pages = LAB_PAGES.get(source.slug, [source.url])

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for url in self.pages:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code != 200:
                    self.logger.warning(f'{self.source.slug} got {resp.status_code} for {url}')
                    continue
                soup = BeautifulSoup(resp.text, 'lxml')
                base_domain = '/'.join(url.split('/')[:3])

                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)

                    if not text or len(text) < 15 or len(text) > 300:
                        continue

                    # Resolve relative URLs
                    if href.startswith('/'):
                        href = f'{base_domain}{href}'
                    elif not href.startswith('http'):
                        continue

                    # Must be same domain
                    if base_domain not in href:
                        continue

                    # Skip navigation/index pages
                    if any(skip in href.lower() for skip in [
                        'login', 'contact', 'annuaire', 'equipe',
                        'formation', 'intranet', 'mentions-legales',
                    ]):
                        continue

                    # Must look like content (news, publication, event, communique)
                    if any(kw in href.lower() for kw in [
                        'actualit', 'news', 'publication', 'article',
                        'event', 'seminaire', 'fait-marquant', 'recherche',
                        'projet', 'communique', 'agenda', 'presse',
                    ]) or any(kw in text.lower() for kw in [
                        'publication', 'paper', 'conference', 'workshop',
                        'thesis', 'soutenance', 'prix', 'award',
                        'inaugur', 'lancement', 'ouverture',
                    ]):
                        if href in seen:
                            continue
                        seen.add(href)

                        articles.append(RawArticle(
                            title=text[:500],
                            url=href,
                            external_id=hashlib.sha256(href.encode()).hexdigest()[:32],
                        ))

            except Exception as e:
                self.logger.warning(f'{self.source.slug} failed for {url}: {e}')

        return articles


# Register for each lab slug
@register_crawler('lig-lab')
class LIGLabCrawler(ResearchLabCrawler):
    """LIG — Laboratoire d'Informatique de Grenoble."""
    pass


@register_crawler('gipsa-lab')
class GIPSALabCrawler(ResearchLabCrawler):
    """GIPSA-lab — Signal, Image, Speech, Automation."""
    pass


@register_crawler('tima-lab')
class TIMALabCrawler(ResearchLabCrawler):
    """TIMA — Techniques of Informatics and Microelectronics."""
    pass


@register_crawler('verimag')
class VERIMAGCrawler(ResearchLabCrawler):
    """VERIMAG — Verification, Modeling and Analysis."""
    pass


@register_crawler('grenoblealpes')
class GrenobleAlpesCrawler(ResearchLabCrawler):
    """Grenoble Alpes Metropole — local government news and events."""
    pass
