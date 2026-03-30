import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource


BASE_URL = 'https://www.leti-cea.com'
PAGES = [
    '/cea-tech/leti/english/Pages/What%27s-On/News/news.aspx',
    '/cea-tech/leti/english/Pages/What%27s-On/Events/events.aspx',
    '/cea-tech/leti/english/Pages/What%27s-On/Press%20release/press-releases.aspx',
]
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.5',
}


@register_crawler('cea-leti')
class CeaLetiCrawler(BaseCrawler):
    """Crawler for CEA-Leti: news, events, and press releases from 3 dedicated pages."""

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen_urls = set()

        for page_path in PAGES:
            url = BASE_URL + page_path
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                page_articles = self._parse_list_page(resp.text, seen_urls)
                self.logger.info(f'CEA-Leti {page_path.split("/")[-1]}: {len(page_articles)} articles')
                articles.extend(page_articles)
            except Exception as e:
                self.logger.warning(f'Failed to fetch {url}: {e}')

        # Also scrape the homepage for featured items
        try:
            resp = requests.get(
                f'{BASE_URL}/cea-tech/leti/english', headers=HEADERS, timeout=20
            )
            homepage_articles = self._parse_homepage(resp.text, seen_urls)
            self.logger.info(f'CEA-Leti homepage: {len(homepage_articles)} additional articles')
            articles.extend(homepage_articles)
        except Exception as e:
            self.logger.warning(f'Failed to fetch homepage: {e}')

        # Fetch detail page content for each article
        for article in articles:
            try:
                content = self._fetch_detail_content(article.url)
                if content:
                    article.content = content
            except Exception as e:
                self.logger.debug(f'Could not fetch detail for {article.url}: {e}')

        return articles

    def _fetch_detail_content(self, url: str) -> str | None:
        """Fetch and extract main text content from a CEA-Leti detail page."""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, 'lxml')

            # Extract paragraphs from #content area or all <p> tags
            content_area = soup.select_one('#content') or soup
            paragraphs = []
            for p in content_area.select('p'):
                text = p.get_text(strip=True)
                if len(text) > 30:
                    paragraphs.append(text)

            if paragraphs:
                return '\n\n'.join(paragraphs)
        except Exception:
            pass
        return None

    def _parse_list_page(self, html: str, seen: set) -> list[RawArticle]:
        """Parse a news/events/press list page."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []

        for a_tag in soup.select('a[href]'):
            href = a_tag.get('href', '')
            text = a_tag.get_text(strip=True)

            # Filter: must be a content link (news, press, event)
            if not text or len(text) < 15:
                continue
            href_lower = href.lower()
            if not any(kw in href_lower for kw in [
                "what's-on", "what%27s-on", "press", "news", "event", "actualite"
            ]):
                continue
            # Skip navigation/meta links
            if any(skip in href_lower for skip in [
                'contact', 'resources', 'gallery', 'press-room'
            ]):
                continue

            full_url = self._resolve_url(href)
            if full_url in seen:
                continue
            seen.add(full_url)

            articles.append(RawArticle(
                title=text[:500],
                url=full_url,
                external_id=self._url_hash(full_url),
                content=None,  # Will be fetched on detail if needed
                published_at=None,
            ))

        return articles

    def _parse_homepage(self, html: str, seen: set) -> list[RawArticle]:
        """Extract featured articles from homepage."""
        soup = BeautifulSoup(html, 'lxml')
        articles = []

        for a_tag in soup.select('a[href]'):
            href = a_tag.get('href', '')
            text = a_tag.get_text(strip=True)

            if not text or len(text) < 20:
                continue
            href_lower = href.lower()
            if not any(kw in href_lower for kw in [
                "what's-on", "what%27s-on", "press", "news", "event", "actualite"
            ]):
                continue
            if any(skip in href_lower for skip in [
                'contact', 'resources', 'gallery', 'press-room',
                'news.aspx', 'events.aspx', 'press-releases.aspx',
            ]):
                continue

            full_url = self._resolve_url(href)
            if full_url in seen:
                continue
            seen.add(full_url)

            articles.append(RawArticle(
                title=text[:500],
                url=full_url,
                external_id=self._url_hash(full_url),
            ))

        return articles

    def _resolve_url(self, href: str) -> str:
        if href.startswith('http'):
            return href
        return f'{BASE_URL}{href}' if href.startswith('/') else f'{BASE_URL}/{href}'

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:32]
