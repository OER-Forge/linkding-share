"""URL body fetching and scraping via trafilatura."""

import httpx
import trafilatura

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
HTTP_TIMEOUT = 15.0

# Sentinel returned when a publisher blocks programmatic access.
BLOCKED_BODY = "\x00BLOCKED\x00"


def _format_body(text: str) -> str:
    paragraphs = [line.rstrip() for line in text.split("\n") if line.rstrip()]
    return "\n\n".join(paragraphs)


async def fetch_body(url: str) -> str:
    """Fetch and extract readable body text. Returns BLOCKED_BODY on 401/403."""
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(headers=headers, timeout=HTTP_TIMEOUT) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return BLOCKED_BODY
            return f"[Failed to load: HTTP {e.response.status_code}]"
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            return f"[Failed to load: {e}]"
    extracted = trafilatura.extract(
        resp.text,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )
    if not extracted:
        return "[Could not extract article body.]"
    return _format_body(extracted)


async def scrape_title(url: str) -> tuple[str, str]:
    """Fetch a URL and extract title + description. Returns ("", "") on failure."""
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(headers=headers, timeout=HTTP_TIMEOUT) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException, httpx.HTTPStatusError):
            return "", ""
    meta = trafilatura.extract_metadata(resp.text, default_url=url)
    if meta is None:
        return "", ""
    return (meta.title or ""), (meta.description or "")
