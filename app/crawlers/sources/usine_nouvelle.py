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
    'https://www.usinenouvelle.com/',
    'https://www.usinenouvelle.com/electronique/',
    'https://www.usinenouvelle.com/numerique/',
]


@register_crawler('usine-nouvelle')
class UsineNouvelleCrawler(BaseCrawler):
    """Crawler for L'Usine Nouvelle - French industrial/tech news (Cloudflare-protected)."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for url in SECTION_URLS:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code == 403:
                    self.logger.warning(f'Usine Nouvelle 403 for {url}')
                    continue
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')

                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)
                    if not text or len(text) < 20:
                        continue
                    if '/article/' not in href and not any(
                        c.isdigit() for c in href[-8:]
                    ):
                        continue
                    if href.startswith('/'):
                        href = f'https://www.usinenouvelle.com{href}'
                    if not href.startswith('https://www.usinenouvelle.com'):
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
                self.logger.warning(f'Usine Nouvelle failed for {url}: {e}')

        return articles
