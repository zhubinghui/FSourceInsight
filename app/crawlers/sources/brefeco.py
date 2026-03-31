import hashlib

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}

SECTION_URLS = [
    'https://www.brefeco.com/',
    'https://www.brefeco.com/actualites',
    'https://www.brefeco.com/actualites/innovation',
    'https://www.brefeco.com/actualites/numerique',
]

# Section index URLs to skip (not articles)
_INDEX_URLS = {url.rstrip('/') for url in SECTION_URLS}


@register_crawler('brefeco')
class BrefEcoCrawler(BaseCrawler):
    """Crawler for BrefEco - Auvergne-Rhone-Alpes regional economic news."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for url in SECTION_URLS:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')

                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)
                    if not text or len(text) < 15:
                        continue
                    if href.startswith('/'):
                        href = f'https://www.brefeco.com{href}'
                    if not href.startswith('https://www.brefeco.com/'):
                        continue
                    # Filter for article-like paths
                    if not any(kw in href for kw in [
                        '/actualite', '/article', '/dossier',
                        '/innovation', '/numerique', '/entreprise',
                    ]):
                        continue
                    # Skip pure section indexes
                    if href.rstrip('/') in _INDEX_URLS:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)

                    articles.append(RawArticle(
                        title=text[:500],
                        url=href,
                        external_id=hashlib.sha256(href.encode()).hexdigest()[:32],
                    ))
            except Exception as e:
                self.logger.warning(f'BrefEco failed for {url}: {e}')

        return articles
