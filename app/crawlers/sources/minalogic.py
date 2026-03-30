import hashlib
import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}


@register_crawler('minalogic')
class MinalogicCrawler(BaseCrawler):
    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()
        for url in [
            'https://www.minalogic.com/en/news/',
            'https://www.minalogic.com/en/events/',
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
                    # News/event article URLs
                    if not any(kw in href for kw in ['/en/news/', '/en/events/', '/en/actualites/']):
                        continue
                    # Skip index pages
                    if href.rstrip('/').endswith(('/news', '/events', '/actualites')):
                        continue
                    full_url = href if href.startswith('http') else f'https://www.minalogic.com{href}'
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    articles.append(RawArticle(
                        title=text[:500], url=full_url,
                        external_id=hashlib.sha256(full_url.encode()).hexdigest()[:32],
                    ))
            except Exception as e:
                self.logger.warning(f'Minalogic failed for {url}: {e}')
        return articles
