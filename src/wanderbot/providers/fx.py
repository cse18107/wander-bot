"""Currency conversion via Frankfurter (real, keyless, ECB rates)."""

from __future__ import annotations

import httpx

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)


class FrankfurterFXProvider:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def convert(self, amount: float, frm: str, to: str) -> float | None:
        frm, to = frm.upper(), to.upper()
        if frm == to:
            return round(amount, 2)
        try:
            resp = await self._http().get(
                f"{self._settings.exchange_rates_base_url}/latest",
                params={"base": frm, "symbols": to},
            )
            if resp.status_code >= 400:
                log.warning("fx_error", status=resp.status_code, frm=frm, to=to)
                return None
            rate = resp.json().get("rates", {}).get(to)
            return round(amount * float(rate), 2) if rate is not None else None
        except Exception as exc:  # pragma: no cover - resilience
            log.warning("fx_failed", error=str(exc))
            return None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
