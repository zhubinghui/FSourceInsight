"""Text cleaning utilities for HTML stripping and content normalization."""
import re
from html import unescape


def strip_html(text: str | None) -> str | None:
    """Remove all HTML tags, decode entities, and normalize whitespace.

    Handles common patterns from RSS feeds:
    - <p>, <a>, <div>, <span>, <br> tags
    - HTML entities like &amp; &#8230; &nbsp;
    - Inline styles and attributes
    - Nested tags
    """
    if not text:
        return text

    # Replace <br> and <br/> with newlines
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)

    # Replace block-level closing tags with newlines for readability
    text = re.sub(r'</(?:p|div|h[1-6]|li|tr|blockquote)>', '\n', text, flags=re.IGNORECASE)

    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities (&#8230; → …, &amp; → &, etc.)
    text = unescape(text)

    # Normalize whitespace: collapse multiple spaces/tabs to single space
    text = re.sub(r'[ \t]+', ' ', text)

    # Normalize newlines: collapse multiple blank lines to single
    text = re.sub(r'\n\s*\n+', '\n\n', text)

    # Strip leading/trailing whitespace per line and overall
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines).strip()

    return text


def clean_article_text(text: str | None, max_length: int = 0) -> str | None:
    """Clean article text: strip HTML, normalize, optionally truncate."""
    text = strip_html(text)
    if text and max_length > 0 and len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + '...'
    return text
