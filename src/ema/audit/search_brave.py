"""Live web search through the Brave Search API, the second `SearchBackend` adapter."""

from __future__ import annotations

import html
import re

import httpx
from pydantic import SecretStr

from ema.audit.research_tools import SearchBackend
from ema.core.config import Settings
from ema.core.errors import EmaError

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
_TAGS = re.compile(r"<[^>]+>")


def _text(value: object) -> str:
    return html.unescape(_TAGS.sub("", value)).strip() if isinstance(value, str) else ""


class BraveSearch:
    """Sends the exact, already guarded query; the key travels only in the request header."""

    def __init__(self, key: SecretStr, client: httpx.Client | None = None) -> None:
        self._key = key
        self._client = client

    def search(self, query: str) -> list[dict[str, str]]:
        headers = {
            "X-Subscription-Token": self._key.get_secret_value(),
            "Accept": "application/json",
        }
        try:
            if self._client is not None:
                response = self._client.get(BRAVE_URL, params={"q": query}, headers=headers)
            else:
                with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
                    response = client.get(BRAVE_URL, params={"q": query}, headers=headers)
        except httpx.HTTPError as exc:
            raise EmaError(
                "search_unavailable", "Căutarea online nu este disponibilă.", type(exc).__name__
            ) from exc
        if response.status_code != 200:
            raise EmaError(
                "search_status", "Căutarea online a răspuns cu eroare.", str(response.status_code)
            )
        try:
            items = response.json().get("web", {}).get("results", [])
            return [
                {
                    "title": _text(item["title"]),
                    "url": str(item["url"]),
                    "snippet": _text(item.get("description")),
                }
                for item in items
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise EmaError(
                "search_response", "Răspunsul căutării este invalid.", type(exc).__name__
            ) from exc


def select_search_backend(settings: Settings, replay: SearchBackend) -> SearchBackend:
    """Live when a Brave key is present and live research is on, otherwise the replay."""
    key = settings.brave_key()
    if settings.research_live and key is not None:
        return BraveSearch(key)
    return replay
