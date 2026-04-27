import hashlib

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}


@register_crawler('tribune-aura')
class TribuneAURACrawler(BaseCrawler):
    """Crawler for La Tribune AURA - Auvergne-Rhone-Alpes regional economic news.

    Each <article> wraps one <a href>; the title lives in an h1 or h2 inside,
    and the description in the first <p>.
    """

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        resp = requests.get(self.source.url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        articles = []
        seen = set()
        for art in soup.select('article'):
            link = art.select_one('a[href]')
            if not link:
                continue
            href = link.get('href', '')
            if '/article/' not in href:
                continue
            if href in seen:
                continue
            seen.add(href)

            heading = art.select_one('h1, h2, h3')
            title = heading.get_text(strip=True) if heading else None
            if not title or len(title) < 10:
                continue

            desc_elem = art.select_one('p')
            description = desc_elem.get_text(strip=True) if desc_elem else None

            img = art.select_one('img')
            image_url = (img.get('src') or img.get('data-src')) if img else None

            articles.append(RawArticle(
                title=title[:500],
                url=href,
                external_id=hashlib.sha256(href.encode()).hexdigest()[:32],
                content=description,
                image_url=image_url,
            ))

        return articles
