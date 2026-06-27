"""Tavily web search adapter (real, AI-native search for the research agent)."""

from __future__ import annotations

import httpx

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger
from wanderbot.providers.base import ProviderError

log = get_logger(__name__)


class TavilySearchResult:
    def __init__(self, title: str, url: str, content: str):
        self.title = title
        self.url = url
        self.content = content


class TavilyImage:
    def __init__(self, url: str, description: str = ""):
        self.url = url
        self.description = description


class TavilyProvider:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def search(self, query: str, max_results: int = 5) -> list[TavilySearchResult]:
        if self._settings.tavily_api_key is None:
            raise ProviderError("tavily_api_key_missing")
        resp = await self._http().post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._settings.tavily_api_key.get_secret_value(),
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
        )
        if resp.status_code >= 400:
            raise ProviderError(f"tavily_error_{resp.status_code}")
        data = resp.json()
        return [
            TavilySearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
            )
            for r in data.get("results", [])
        ]

    async def images(self, query: str, max_results: int = 8) -> list[TavilyImage]:
        """Fetch query-related images (include_images + descriptions)."""
        if self._settings.tavily_api_key is None:
            raise ProviderError("tavily_api_key_missing")
        resp = await self._http().post(
            "https://api.tavily.com/search",
            json={
                "api_key": self._settings.tavily_api_key.get_secret_value(),
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_images": True,
                "include_image_descriptions": True,
            },
        )
        if resp.status_code >= 400:
            raise ProviderError(f"tavily_error_{resp.status_code}")
        return self._parse_images(resp.json())

    @staticmethod
    def _parse_images(data: dict) -> list[TavilyImage]:
        out: list[TavilyImage] = []
        for img in data.get("images", []) or []:
            if isinstance(img, str):
                out.append(TavilyImage(url=img))
            elif isinstance(img, dict) and img.get("url"):
                out.append(TavilyImage(url=img["url"], description=img.get("description", "")))
        return out

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
