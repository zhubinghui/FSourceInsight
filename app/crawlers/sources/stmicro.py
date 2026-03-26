from app.crawlers.registry import register_crawler
from app.crawlers.rss_crawler import RSSCrawler
from app.crawlers.base import RawArticle


@register_crawler('stmicroelectronics')
class STMicroCrawler(RSSCrawler):
    """Crawler for STMicroelectronics newsroom - semiconductor news from Crolles/Grenoble."""

    def parse_entry(self, entry) -> RawArticle | None:
        article = super().parse_entry(entry)
        if article:
            # STMicro newsroom entries often have category tags
            tags = [t.get('term', '') for t in entry.get('tags', [])]
            if tags:
                # Store tags in content as metadata hint for LLM classification
                tag_line = f'[Tags: {", ".join(tags)}]'
                if article.content:
                    article.content = f'{tag_line}\n{article.content}'
                else:
                    article.content = tag_line
        return article
