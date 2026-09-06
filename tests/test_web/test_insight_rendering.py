from bs4 import BeautifulSoup

from app.models.article import Article
from app.models.source import NewsSource


def test_article_renders_markdown_but_never_trusts_html(client, db):
    source = NewsSource(name='Synthetic source', slug='synthetic', url='https://test.invalid', category='national')
    db.session.add(source)
    db.session.flush()
    article = Article(source_id=source.id, url='https://test.invalid/news', title_fr='Safe title',
                      insight_zh='''# <img src=x onerror=alert(1)> Heading
**Important** & ordinary text
- <svg onload=alert(1)>Item</svg>
| Name | Value |
| --- | --- |
| **Research** | <script>alert(1)</script> |
<a href="javascript:alert(1)">link</a>
[click](javascript:alert(1))''')
    db.session.add(article)
    db.session.commit()
    response = client.get(f'/news/{article.id}')
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, 'html.parser')
    assert soup.select('[onerror], [onload], a[href^="javascript:"]') == []
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;img' in response.text
    assert soup.find('strong', string='Important') is not None
    assert soup.find('strong', string='Research') is not None
    assert soup.select_one('table.insight-table tbody td') is not None
