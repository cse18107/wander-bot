"""Diagnostic: see exactly what Duffel Stays returns (raw status + body).

Run from project root with .venv active:
    python scripts/check_stays.py
A 403/404 usually means Stays isn't enabled on your org (Dashboard -> Stays).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

from wanderbot.config import get_settings

# Duffel sandbox test-hotel coordinates — the ONLY place hotels appear in test mode.
LAT, LON = -24.38, -128.32


async def main() -> None:
    s = get_settings()
    if s.duffel_api_key is None:
        print("❌ WB_DUFFEL_API_KEY not set.")
        return

    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=5)
    body = {
        "data": {
            "rooms": 1,
            "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(),
            "guests": [{"type": "adult"}, {"type": "adult"}],
            "location": {
                "radius": 10,
                "geographic_coordinates": {"latitude": LAT, "longitude": LON},
            },
        }
    }
    headers = {
        "Authorization": f"Bearer {s.duffel_api_key.get_secret_value()}",
        "Duffel-Version": s.duffel_version,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    print(f"POST /stays/search  test-hotels({LAT},{LON})  {check_in} -> {check_out}")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.duffel.com/stays/search", json=body, headers=headers
        )
    print(f"status = {resp.status_code}")
    if resp.status_code >= 400:
        print("body:", resp.text[:600])
        if resp.status_code in (403, 404):
            print("→ Stays is likely not enabled on your org. Enable it in the Duffel dashboard.")
        return
    results = resp.json().get("data", {}).get("results", [])
    print(f"✅ {len(results)} stay(s) returned")
    for r in results[:3]:
        acc = r.get("accommodation", {})
        print(f"   {acc.get('name')}  {r.get('cheapest_rate_total_amount')} {r.get('cheapest_rate_currency')}")


if __name__ == "__main__":
    asyncio.run(main())
