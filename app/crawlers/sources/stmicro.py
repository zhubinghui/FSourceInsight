import hashlib
import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}


@register_crawler('stmicroelectronics')
class STMicroCrawler(BaseCrawler):
    """Crawler for STMicroelectronics newsroom."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for page_url in [
            'https://newsroom.st.com/',
            'https://newsroom.st.com/all-news/corporate',
            'https://newsroom.st.com/all-news/product-technology',
        ]:
            try:
                resp = requests.get(page_url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'lxml')

                for a_tag in soup.select('a[href]'):
                    href = a_tag.get('href', '')
                    text = a_tag.get_text(strip=True)
                    if not text or len(text) < 20:
                        continue
                    # Match newsroom press items, blog posts, and content pages
                    if not any(kw in href for kw in [
                        '/media-center/press-item', '/all-news/',
                        'blog.st.com/', '/content/st_com/',
                    ]):
                        continue
                    # Skip category index pages
                    if href.rstrip('/').endswith(('/corporate', '/product-technology', '/manufacturing', '/feature')):
                        continue
                    full_url = href if href.startswith('http') else f'https://newsroom.st.com{href}'
                    if full_url in seen:
                        continue
                    seen.add(full_url)
                    articles.append(RawArticle(
                        title=text[:500], url=full_url,
                        external_id=hashlib.sha256(full_url.encode()).hexdigest()[:32],
                    ))
            except Exception as e:
                self.logger.warning(f'STMicro failed for {page_url}: {e}')

        return articles
