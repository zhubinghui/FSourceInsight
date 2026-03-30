import hashlib
import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}


@register_crawler('monde-informatique')
class MondeInformatiqueCrawler(BaseCrawler):
    """Crawler for Le Monde Informatique (RSS broken, HTML scrape)."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        resp = requests.get('https://www.lemondeinformatique.fr/', headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        articles = []
        seen = set()
        for a_tag in soup.select('a[href]'):
            href = a_tag.get('href', '')
            text = a_tag.get_text(strip=True)
            if not text or len(text) < 20:
                continue
            if not href.startswith('https://www.lemondeinformatique.fr/actualites/'):
                continue
            if href in seen:
                continue
            seen.add(href)
            articles.append(RawArticle(
                title=text[:500], url=href,
                external_id=hashlib.sha256(href.encode()).hexdigest()[:32],
            ))
        return articles
