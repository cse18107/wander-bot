"""Typical seasonal weather via Open-Meteo historical archive (real, keyless).

For a future trip we can't get a forecast, so we summarize what the weather was
like at the same location and calendar dates *last year* (ERA5 archive) — a good
proxy for "what season it'll be" (rainy / sunny / windy).
"""

from __future__ import annotations

from datetime import date

import httpx

from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def _shift_year(d: date, year: int) -> date:
    try:
        return d.replace(year=year)
    except ValueError:  # Feb 29 -> Feb 28
        return d.replace(year=year, day=28)


def _condition(avg_max: float, precip_per_day: float, wind_max: float) -> str:
    if precip_per_day >= 6:
        return "Wet / rainy"
    if wind_max >= 35:
        return "Windy"
    if avg_max >= 30:
        return "Hot & sunny"
    if avg_max >= 22:
        return "Warm & pleasant"
    if avg_max >= 12:
        return "Mild / cool"
    return "Cold"


class OpenMeteoWeatherProvider:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=12.0)
        return self._client

    async def typical_weather(
        self, lat: float, lon: float, start: date, end: date
    ) -> dict | None:
        py = (start.year - 1) if start.year >= date.today().year else start.year
        s, e = _shift_year(start, py), _shift_year(end, py)
        resp = await self._http().get(
            _ARCHIVE,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": s.isoformat(),
                "end_date": e.isoformat(),
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                "timezone": "auto",
            },
        )
        if resp.status_code >= 400:
            log.warning("weather_archive_error", status=resp.status_code)
            return None
        daily = resp.json().get("daily", {})
        tmax = [x for x in daily.get("temperature_2m_max", []) if x is not None]
        tmin = [x for x in daily.get("temperature_2m_min", []) if x is not None]
        precip = [x for x in daily.get("precipitation_sum", []) if x is not None]
        wind = [x for x in daily.get("wind_speed_10m_max", []) if x is not None]
        if not tmax:
            return None

        avg_max = sum(tmax) / len(tmax)
        avg_min = sum(tmin) / len(tmin) if tmin else avg_max
        precip_per_day = (sum(precip) / len(precip)) if precip else 0.0
        wind_max = max(wind) if wind else 0.0
        cond = _condition(avg_max, precip_per_day, wind_max)
        summary = (
            f"{cond}. Typically {avg_min:.0f}–{avg_max:.0f}°C, "
            f"~{precip_per_day:.0f}mm/day rain, winds to {wind_max:.0f} km/h "
            f"(based on {s.strftime('%b %Y')})."
        )
        return {
            "summary": summary,
            "condition": cond,
            "temp_max": round(avg_max),
            "temp_min": round(avg_min),
            "precip_mm": round(precip_per_day, 1),
            "wind_kmh": round(wind_max),
        }

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
