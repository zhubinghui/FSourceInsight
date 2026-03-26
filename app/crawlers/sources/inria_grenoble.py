from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler
from app.crawlers.base import RawArticle


@register_crawler('inria-grenoble')
class InriaGrenobleCrawler(RSSCrawler):
    """Crawler for Inria Grenoble - computer science and applied mathematics research."""

    def parse_entry(self, entry) -> RawArticle | None:
        article = super().parse_entry(entry)
        if not article:
            return None

        # Inria feed covers all centers — filter for Grenoble-related content
        # Check tags and content for Grenoble mentions
        tags = [t.get('term', '').lower() for t in entry.get('tags', [])]
        text = (article.title + ' ' + (article.content or '')).lower()

        grenoble_keywords = ['grenoble', 'alpes', 'rhône-alpes', 'rhone-alpes', 'isère', 'isere']
        is_grenoble = any(kw in text for kw in grenoble_keywords)
        has_grenoble_tag = any(kw in tag for tag in tags for kw in grenoble_keywords)

        # Accept all Inria articles but could optionally filter
        if tags:
            tag_line = f'[Tags: {", ".join(t.get("term", "") for t in entry.get("tags", []))}]'
            if article.content:
                article.content = f'{tag_line}\n{article.content}'
            else:
                article.content = tag_line

        return article
