import hashlib

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}

SECTION_URLS = [
    'https://www.linksium.fr/nos-startups',
    'https://www.linksium.fr/actualites',
]


@register_crawler('linksium')
class LinksiumCrawler(BaseCrawler):
    """Crawler for Linksium — Grenoble tech transfer office.

    Crawls both the startup portfolio page (to discover new spin-offs) and
    the news page (for ecosystem updates, incubation announcements).
    """

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
                    if not text or len(text) < 10:
                        continue
                    if href.startswith('/'):
                        href = f'https://www.linksium.fr{href}'
                    if not href.startswith('https://www.linksium.fr/'):
                        continue
                    # Keep startup profiles, news articles, and portfolio entries
                    if not any(kw in href for kw in [
                        '/startup', '/actualite', '/article',
                        '/nos-startups/', '/post/',
                    ]):
                        continue
                    # Skip pure index pages
                    if href.rstrip('/') in {
                        'https://www.linksium.fr/nos-startups',
                        'https://www.linksium.fr/actualites',
                    }:
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
                self.logger.warning(f'Linksium failed for {url}: {e}')

        return articles
