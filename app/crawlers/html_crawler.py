import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from app.models.source import NewsSource
from .base import BaseCrawler, RawArticle


class HTMLCrawler(BaseCrawler):
    """Generic HTML scraper. Subclass and define CSS selectors for source-specific parsing."""

    # Override these in subclasses
    ARTICLE_LIST_SELECTOR = 'article'
    TITLE_SELECTOR = 'h2 a'
    LINK_SELECTOR = 'h2 a'
    CONTENT_SELECTOR = '.content'
    DATE_SELECTOR = 'time'
    AUTHOR_SELECTOR = '.author'
    IMAGE_SELECTOR = 'img'
    DATE_FORMAT = '%Y-%m-%d'

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.5',
    }
    TIMEOUT = 30

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        response = requests.get(
            self.source.url, headers=self.HEADERS, timeout=self.TIMEOUT
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or 'utf-8'

        soup = BeautifulSoup(response.text, 'lxml')
        article_elements = soup.select(self.ARTICLE_LIST_SELECTOR)

        articles = []
        for elem in article_elements:
            try:
                article = self.parse_element(elem)
                if article:
                    articles.append(article)
            except Exception as e:
                self.logger.warning(f'Failed to parse element: {e}')
                continue

        return articles

    def parse_element(self, elem) -> RawArticle | None:
        """Parse a single HTML element into a RawArticle. Override for custom logic."""
        link_elem = elem.select_one(self.LINK_SELECTOR)
        if not link_elem:
            return None

        title = self._extract_title(elem)
        url = self._resolve_url(link_elem.get('href', ''))
        if not title or not url:
            return None

        return RawArticle(
            title=title,
            url=url,
            external_id=self._url_hash(url),
            content=self._extract_text(elem, self.CONTENT_SELECTOR),
            author=self._extract_text(elem, self.AUTHOR_SELECTOR),
            image_url=self._extract_image_url(elem),
            published_at=self._extract_date(elem),
        )

    def _extract_title(self, elem) -> str | None:
        title_elem = elem.select_one(self.TITLE_SELECTOR)
        if title_elem:
            return title_elem.get_text(strip=True)
        return None

    def _extract_text(self, elem, selector: str) -> str | None:
        target = elem.select_one(selector)
        if target:
            return target.get_text(strip=True)
        return None

    def _extract_image_url(self, elem) -> str | None:
        img = elem.select_one(self.IMAGE_SELECTOR)
        if img:
            return img.get('src') or img.get('data-src')
        return None

    def _extract_date(self, elem) -> datetime | None:
        date_elem = elem.select_one(self.DATE_SELECTOR)
        if not date_elem:
            return None

        # Try datetime attribute first (common in <time> tags)
        dt_str = date_elem.get('datetime')
        if dt_str:
            try:
                return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            except ValueError:
                pass

        # Fall back to text content
        text = date_elem.get_text(strip=True)
        try:
            return datetime.strptime(text, self.DATE_FORMAT)
        except ValueError:
            return None

    def _resolve_url(self, href: str) -> str:
        if not href:
            return ''
        url = urljoin(self.source.url, href)
        parsed = urlsplit(url)
        return url if parsed.scheme in {'http', 'https'} and parsed.hostname else ''

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:32]
