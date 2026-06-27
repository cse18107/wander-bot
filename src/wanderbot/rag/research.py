"""Research orchestration: KB (RAG) + live web search, with citations.

Combines grounded knowledge-base retrieval with optional live Tavily search and
returns notes plus the sources backing them. Untrusted web/RAG content is treated
as data, never instructions (the guardrail content-rail enforces this in Phase 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wanderbot.observability.logging import get_logger
from wanderbot.rag.retriever import HybridRetriever

log = get_logger(__name__)


@dataclass
class ResearchResult:
    notes: str
    citations: list[str] = field(default_factory=list)


class Researcher:
    def __init__(self, retriever: HybridRetriever, web=None):  # web: TavilyProvider | None
        self._retriever = retriever
        self._web = web

    async def research(self, query: str, k: int = 4) -> ResearchResult:
        chunks = await self._retriever.retrieve(query, k=k)
        notes_parts: list[str] = []
        citations: list[str] = []
        for c in chunks:
            notes_parts.append(c.text)
            citations.append(c.source)

        if self._web is not None:
            try:
                from wanderbot.security.engine import guard_content

                results = await self._web.search(query, max_results=3)
                for r in results:
                    # Web results are UNTRUSTED -> content rail (Bedrock or regex).
                    safe = await guard_content(f"{r.title}: {r.content[:200]}")
                    notes_parts.append(safe.text)
                    citations.append(r.url)
            except Exception as exc:  # pragma: no cover - degrade gracefully
                log.warning("web_search_failed", error=str(exc))

        notes = "\n".join(notes_parts) if notes_parts else f"No grounded notes for: {query}"
        return ResearchResult(notes=notes, citations=citations)

    async def fetch_images(self, query: str, n: int = 8) -> list[str]:
        """Destination/activity image URLs (empty if web search unavailable)."""
        if self._web is None:
            return []
        try:
            images = await self._web.images(query, max_results=n)
            return [img.url for img in images]
        except Exception as exc:  # pragma: no cover - degrade gracefully
            log.warning("image_fetch_failed", error=str(exc))
            return []
