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


@register_crawler('usine-digitale')
class UsineDigitaleCrawler(BaseCrawler):
    """Crawler for L'Usine Digitale - RSS is blocked, scrape the homepage and section pages."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for url in [
            'https://www.usine-digitale.fr/',
            'https://www.usine-digitale.fr/semi-conducteurs/',
            'https://www.usine-digitale.fr/intelligence-artificielle/',
            'https://www.usine-digitale.fr/cybersecurite/',
        ]:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code == 403:
                    self.logger.warning(f'Usine Digitale 403 for {url}')
                    continue
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')

                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)
                    if not text or len(text) < 20:
                        continue
                    # Content URLs usually end with .N<digits>
                    if not any(c.isdigit() for c in href[-8:]):
                        continue
                    if href.startswith('/'):
                        href = f'https://www.usine-digitale.fr{href}'
                    if not href.startswith('https://www.usine-digitale.fr/'):
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
                self.logger.warning(f'Usine Digitale failed for {url}: {e}')

        return articles
