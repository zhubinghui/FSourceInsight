import hashlib
from datetime import datetime

import feedparser

from app.models.source import NewsSource
from .base import BaseCrawler, RawArticle


class RSSCrawler(BaseCrawler):
    """Generic RSS/Atom feed crawler. Subclass to override parse_entry() for source-specific logic."""

    def __init__(self, source: NewsSource):
        super().__init__(source)
        if not source.feed_url:
            raise ValueError(f'Source {source.name} has no feed_url configured')

    USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0'

    def fetch_articles(self) -> list[RawArticle]:
        import requests

        # One transport path: feedparser parses bytes and never hides HTTP errors
        # by fetching the URL again without our timeout/headers.
        self.empty_result_is_valid = False
        resp = requests.get(
            self.source.feed_url,
            headers={'User-Agent': self.USER_AGENT, 'Accept': 'application/rss+xml, application/xml, text/xml'},
            timeout=30,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        self.empty_result_is_valid = bool(feed.version) and not feed.bozo and not feed.entries

        if feed.bozo and not feed.entries:
            raise RuntimeError(
                f'Failed to parse feed {self.source.feed_url}: {feed.bozo_exception}'
            )

        articles = []
        for entry in feed.entries:
            try:
                article = self.parse_entry(entry)
                if article:
                    articles.append(article)
            except Exception as e:
                self.logger.warning(f'Failed to parse entry: {e}')
                continue

        return articles

    def parse_entry(self, entry) -> RawArticle | None:
        """Parse a single feed entry into a RawArticle. Override for source-specific logic."""
        title = entry.get('title', '').strip()
        link = entry.get('link', '').strip()

        if not title or not link:
            return None

        external_id = entry.get('id') or entry.get('guid') or self._url_hash(link)
        content = self._extract_content(entry)
        author = entry.get('author')
        image_url = self._extract_image(entry)
        published_at = self._parse_date(entry)

        return RawArticle(
            title=title,
            url=link,
            external_id=str(external_id),
            content=content,
            author=author,
            image_url=image_url,
            published_at=published_at,
        )

    def _extract_content(self, entry) -> str | None:
        """Extract content from feed entry, preferring full content over summary."""
        if 'content' in entry and entry.content:
            return entry.content[0].get('value', '')
        return entry.get('summary') or entry.get('description')

    def _extract_image(self, entry) -> str | None:
        """Try to extract an image URL from the entry."""
        # Check media_content
        media = entry.get('media_content', [])
        if media:
            for m in media:
                if 'url' in m:
                    return m['url']

        # Check media_thumbnail
        thumbs = entry.get('media_thumbnail', [])
        if thumbs:
            return thumbs[0].get('url')

        # Check enclosures
        for enc in entry.get('enclosures', []):
            if enc.get('type', '').startswith('image/'):
                return enc.get('href') or enc.get('url')

        return None

    def _parse_date(self, entry) -> datetime | None:
        """Parse published date from entry."""
        for field in ('published_parsed', 'updated_parsed'):
            parsed = entry.get(field)
            if parsed:
                try:
                    # feedparser already returns UTC; do not interpret it in
                    # the worker's local timezone (including its DST offset).
                    return datetime(*parsed[:6])
                except (ValueError, OverflowError):
                    continue
        return None

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:32]
