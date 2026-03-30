import hashlib
import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}


@register_crawler('place-grenet')
class PlaceGrenetCrawler(BaseCrawler):
    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()
        for url in [
            'https://www.placegrenet.fr/category/economie/',
            'https://www.placegrenet.fr/category/science-et-environnement/',
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
                    # PlaceGrenet articles: /2026/03/26/article-slug
                    if 'placegrenet.fr/20' not in href:
                        continue
                    if href in seen:
                        continue
                    seen.add(href)
                    articles.append(RawArticle(
                        title=text[:500], url=href,
                        external_id=hashlib.sha256(href.encode()).hexdigest()[:32],
                    ))
            except Exception as e:
                self.logger.warning(f'Place Grenet failed for {url}: {e}')
        return articles
