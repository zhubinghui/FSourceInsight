"""Fetch a company website and extract a clean text excerpt for LLM analysis."""
import logging

from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from app.crawlers.fetcher import FetchError, FetchPolicy, SafeFetcher

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9,fr-FR;q=0.7,zh-CN;q=0.5',
}
TIMEOUT = 15
MAX_CHARS = 5000
MIN_USEFUL_CHARS = 200  # Below this we treat the page as JS-rendered / empty


def fetch_website_excerpt(url: str) -> tuple[str | None, str]:
    """Fetch a URL and return a cleaned text excerpt.

    Returns (excerpt, status) where status is one of:
      - 'ok'         : excerpt has at least MIN_USEFUL_CHARS of text
      - 'too_thin'   : page loaded but extracted text is too short (likely SPA)
      - 'http_error' : non-2xx response
      - 'fetch_error': network/timeout/exception
    """
    if not url:
        return None, 'fetch_error'

    try:
        policy = FetchPolicy(allowed_hosts=(urlsplit(url).hostname,), max_seconds=TIMEOUT)
        with SafeFetcher(policy) as fetcher:
            response = fetcher.fetch(url)
    except ValueError:
        return None, 'fetch_error'
    except FetchError as exc:
        logger.info('website fetch failed: %s', exc.code)
        status = 'http_error' if exc.code in {'forbidden', 'robots_denied', 'http_error',
                                             'server_error', 'rate_limited'} else 'fetch_error'
        return None, status

    soup = BeautifulSoup(response.body, 'lxml')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'footer', 'header', 'iframe']):
        tag.decompose()

    text = soup.get_text(separator=' ', strip=True)
    text = ' '.join(text.split())

    if len(text) < MIN_USEFUL_CHARS:
        return None, 'too_thin'

    return text[:MAX_CHARS], 'ok'
