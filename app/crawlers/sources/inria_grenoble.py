import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept-Language': 'en-US,en;q=0.9',
}


@register_crawler('inria-grenoble')
class InriaGrenobleCrawler(BaseCrawler):
    """Crawler for Inria news page (RSS is 404, use HTML scraping)."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for url in [
            'https://www.inria.fr/en/news',
            'https://www.inria.fr/en/events',
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
                    # Filter for content pages
                    if not any(kw in href for kw in ['/en/', '/fr/']):
                        continue
                    # Skip navigation
                    if href.endswith('/news') or href.endswith('/events'):
                        continue

                    full_url = href if href.startswith('http') else f'https://www.inria.fr{href}'
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    # Try to extract date from sibling elements
                    pub_date = None
                    parent = a_tag.find_parent(['article', 'div', 'li'])
                    if parent:
                        time_el = parent.find('time')
                        if time_el and time_el.get('datetime'):
                            try:
                                pub_date = datetime.fromisoformat(
                                    time_el['datetime'].replace('Z', '+00:00')
                                )
                            except ValueError:
                                pass

                    articles.append(RawArticle(
                        title=text[:500],
                        url=full_url,
                        external_id=hashlib.sha256(full_url.encode()).hexdigest()[:32],
                        published_at=pub_date,
                    ))
            except Exception as e:
                self.logger.warning(f'Inria fetch failed for {url}: {e}')

        return articles
