"""Linkding REST API client."""

from __future__ import annotations

from datetime import datetime

import httpx

from .config import Config
from .models import Bookmark

HTTP_TIMEOUT = 20.0


def _bookmark_from_dict(d: dict) -> Bookmark:
    date_added = None
    raw_date = d.get("date_added")
    if raw_date:
        try:
            date_added = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    return Bookmark(
        id=int(d["id"]),
        url=d.get("url", ""),
        title=d.get("title", ""),
        description=d.get("description", ""),
        tag_names=[t for t in d.get("tag_names", []) if isinstance(t, str)],
        date_added=date_added,
        website_title=d.get("website_title"),
        website_description=d.get("website_description"),
    )


def _auth_headers(cfg: Config) -> dict[str, str]:
    return {"Authorization": f"Token {cfg.linkding.api_key}"}


async def fetch_tags(cfg: Config) -> tuple[list[str], str | None]:
    """Return (tag_names, error). Paginates automatically."""
    headers = _auth_headers(cfg)
    tags: list[str] = []
    url: str | None = f"{cfg.linkding.url}/api/tags/?limit=1000"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        while url:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return [], "Authentication failed — check api_key"
                return [], f"HTTP {e.response.status_code}"
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                return [], f"Request failed: {e}"
            data = resp.json()
            for t in data.get("results", []):
                if isinstance(t, dict) and "name" in t:
                    tags.append(t["name"])
            url = data.get("next")
    return tags, None


async def fetch_bookmarks(cfg: Config) -> tuple[list[Bookmark], str | None]:
    """Fetch all bookmarks from linkding, paginated. Returns (bookmarks, error)."""
    headers = _auth_headers(cfg)
    bookmarks: list[Bookmark] = []
    url: str | None = f"{cfg.linkding.url}/api/bookmarks/?limit=100"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        while url:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    return [], "Authentication failed — check api_key"
                return [], f"HTTP {e.response.status_code}"
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                return [], f"Request failed: {e}"
            data = resp.json()
            for item in data.get("results", []):
                try:
                    bookmarks.append(_bookmark_from_dict(item))
                except (KeyError, ValueError, TypeError):
                    continue
            url = data.get("next")
    return bookmarks, None


async def create_bookmark(
    cfg: Config,
    url: str,
    title: str = "",
    description: str = "",
    tag_names: list[str] | None = None,
) -> tuple[bool, str, Bookmark | None]:
    headers = {**_auth_headers(cfg), "Content-Type": "application/json"}
    payload: dict[str, object] = {"url": url}
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    if tag_names:
        payload["tag_names"] = tag_names
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(f"{cfg.linkding.url}/api/bookmarks/", headers=headers, json=payload)
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        return False, f"Request failed: {e}", None
    if resp.status_code in (200, 201):
        try:
            return True, "Bookmark saved", _bookmark_from_dict(resp.json())
        except Exception:
            return True, "Bookmark saved", None
    if resp.status_code in (401, 403):
        return False, "Authentication failed — check api_key", None
    return False, f"Error {resp.status_code}: {resp.text[:120]}", None


async def update_bookmark(
    cfg: Config,
    bookmark_id: int,
    title: str,
    description: str,
    tag_names: list[str],
) -> tuple[bool, str, Bookmark | None]:
    headers = {**_auth_headers(cfg), "Content-Type": "application/json"}
    payload = {"title": title, "description": description, "tag_names": tag_names}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.patch(
                f"{cfg.linkding.url}/api/bookmarks/{bookmark_id}/",
                headers=headers,
                json=payload,
            )
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        return False, f"Request failed: {e}", None
    if resp.status_code in (200, 201):
        try:
            return True, "Bookmark updated", _bookmark_from_dict(resp.json())
        except Exception:
            return True, "Bookmark updated", None
    if resp.status_code in (401, 403):
        return False, "Authentication failed — check api_key", None
    return False, f"Error {resp.status_code}: {resp.text[:120]}", None


async def delete_bookmark(cfg: Config, bookmark_id: int) -> tuple[bool, str]:
    headers = _auth_headers(cfg)
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.delete(
                f"{cfg.linkding.url}/api/bookmarks/{bookmark_id}/",
                headers=headers,
            )
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        return False, f"Request failed: {e}"
    if resp.status_code == 204:
        return True, "Bookmark deleted"
    if resp.status_code in (401, 403):
        return False, "Authentication failed — check api_key"
    if resp.status_code == 404:
        return False, "Bookmark not found"
    return False, f"Error {resp.status_code}: {resp.text[:120]}"
