import hashlib

import requests
from bs4 import BeautifulSoup

from app.crawlers.registry import register_crawler
from app.crawlers.base import BaseCrawler, RawArticle
from app.models.source import NewsSource

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9',
}


@register_crawler('linksium')
class LinksiumCrawler(BaseCrawler):
    """Crawler for Linksium — Grenoble tech transfer office.

    The /nos-startups page uses Craft CMS + Blitz SSR. Startup data is embedded
    in data-* attributes on <li> elements (data-name, data-description, data-year,
    data-link, data-project-url). No JS rendering needed.
    """

    def __init__(self, source: NewsSource):
        super().__init__(source)

    def fetch_articles(self) -> list[RawArticle]:
        articles = []
        seen = set()

        # 1. Startup portfolio — extract from data-* attributes
        try:
            resp = requests.get(
                'https://www.linksium.fr/nos-startups', headers=HEADERS, timeout=20
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'lxml')

            for item in soup.select('[data-name][data-description]'):
                name = item.get('data-name', '').strip()
                desc = item.get('data-description', '').strip()
                year = item.get('data-year', '').strip()
                link = item.get('data-link', '').strip()
                project_url = item.get('data-project-url', '').strip()

                if not name or not desc or len(name) < 2:
                    continue
                # Skip navigation/category headers
                if name.lower() in ('calque 1', 'nos startups créées récemment',
                                    'santé', 'numérique et électronique',
                                    'energie et environnement', 'chimie et matériaux',
                                    'sciences humaines et sociales'):
                    continue

                url = project_url or (f'https://{link}' if link and not link.startswith('http') else link) or f'https://www.linksium.fr/nos-startups#{name}'
                ext_id = hashlib.sha256(f'linksium:{name}'.encode()).hexdigest()[:32]

                if ext_id in seen:
                    continue
                seen.add(ext_id)

                title = f'{name} ({year})' if year else name
                content = desc

                articles.append(RawArticle(
                    title=title,
                    url=url,
                    external_id=ext_id,
                    content=content,
                ))
        except Exception as e:
            self.logger.warning(f'Linksium startup portfolio failed: {e}')

        # 2. News/actualites page
        try:
            resp = requests.get(
                'https://www.linksium.fr/actualites', headers=HEADERS, timeout=20
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'lxml')

            for a_tag in soup.select('a[href]'):
                href = a_tag.get('href', '')
                text = a_tag.get_text(strip=True)
                if not text or len(text) < 15:
                    continue
                if href.startswith('/'):
                    href = f'https://www.linksium.fr{href}'
                if not href.startswith('https://www.linksium.fr/'):
                    continue
                if '/actualite' not in href and '/post/' not in href:
                    continue
                if href.rstrip('/') == 'https://www.linksium.fr/actualites':
                    continue

                ext_id = hashlib.sha256(href.encode()).hexdigest()[:32]
                if ext_id in seen:
                    continue
                seen.add(ext_id)

                articles.append(RawArticle(
                    title=text[:500],
                    url=href,
                    external_id=ext_id,
                ))
        except Exception as e:
            self.logger.warning(f'Linksium news failed: {e}')

        return articles
