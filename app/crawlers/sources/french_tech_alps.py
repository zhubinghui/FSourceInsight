import hashlib
import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}


@register_crawler('french-tech-alps')
class FrenchTechAlpsCrawler(BaseCrawler):
    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()
        for url in [
            'https://www.ftalps.com/actualites-generales/',
            'https://www.ftalps.com/evenements/',
        ]:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')
                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)
                    if not text or len(text) < 15:
                        continue
                    if 'ftalps.com/' not in href:
                        continue
                    # Skip navigation/directory pages
                    if any(kw in href for kw in ['/directory/', '/a-propos/', '/carte-', '/les-appels', '/territoires/', 'annuaire', 'accueil-']):
                        continue
                    # Must look like a content page (not index)
                    parts = href.rstrip('/').split('/')
                    if len(parts) < 5:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)
                    articles.append(RawArticle(
                        title=text[:500], url=href,
                        external_id=hashlib.sha256(href.encode()).hexdigest()[:32],
                    ))
            except Exception as e:
                self.logger.warning(f'FT Alps failed for {url}: {e}')
        return articles
