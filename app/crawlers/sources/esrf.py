import hashlib

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
}


@register_crawler('esrf')
class ESRFCrawler(BaseCrawler):
    """Crawler for ESRF (HTML scrape, RSS returns 403)."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for url in [
            'https://www.esrf.fr/home/news.html',
            'https://www.esrf.fr/home/events.html',
            'https://www.esrf.fr/home/news/general-news.html',
        ]:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                if resp.status_code != 200:
                    self.logger.warning(f'ESRF {resp.status_code} for {url}')
                    continue
                soup = BeautifulSoup(resp.text, 'lxml')

                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)
                    if not text or len(text) < 15:
                        continue
                    href_lower = href.lower()
                    if not any(kw in href_lower for kw in ['/news/', '/events/', '/general-news/']):
                        continue
                    # Skip index pages
                    if href_lower.rstrip('/').endswith(('news', 'events', 'general-news')):
                        continue

                    full_url = href if href.startswith('http') else f'https://www.esrf.fr{href}'
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    articles.append(RawArticle(
                        title=text[:500],
                        url=full_url,
                        external_id=hashlib.sha256(full_url.encode()).hexdigest()[:32],
                    ))
            except Exception as e:
                self.logger.warning(f'ESRF failed for {url}: {e}')

        return articles
