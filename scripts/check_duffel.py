"""Diagnostic: verify your Duffel token returns real flight offers.

Run from the project root (with .venv activated):
    python scripts/check_duffel.py
    python scripts/check_duffel.py LAX SFO     # custom origin/destination
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta

from wanderbot.config import get_settings
from wanderbot.domain import FlightSearchQuery
from wanderbot.providers.duffel.flights import DuffelFlightProvider


async def main() -> None:
    origin = sys.argv[1] if len(sys.argv) > 1 else "JFK"
    destination = sys.argv[2] if len(sys.argv) > 2 else "LHR"

    s = get_settings()
    print(f"flight_provider = {s.flight_provider}")
    if s.duffel_api_key is None:
        print("❌ WB_DUFFEL_API_KEY is not set (blank). Add a real duffel_test_ token to .env.")
        return
    key = s.duffel_api_key.get_secret_value()
    print(f"token prefix = {key[:11]!r}  (length {len(key)})")
    if key.startswith("duffel_test_...") or key.endswith("..."):
        print("❌ That looks like the placeholder from .env.example — paste your real token.")
        return

    dep = date.today() + timedelta(days=30)
    print(f"searching {origin} -> {destination} on {dep} ...")
    provider = DuffelFlightProvider()
    try:
        offers = await provider.search_flights(
            FlightSearchQuery(origin=origin, destination=destination, departure_date=dep, adults=1)
        )
        print(f"✅ auth OK — {len(offers)} offer(s) returned")
        for o in offers[:3]:
            seg = o.segments[0]
            print(f"   {o.origin}->{o.destination}  {o.price}  {o.stops} stop(s)  {seg.carrier}{seg.flight_number}")
        if not offers:
            print("   (auth works but no sandbox inventory for this route/date — try LHR->JFK or a major route)")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ ERROR: {type(exc).__name__}: {exc}")
        print("   401 => token is wrong/placeholder. Other => network or route issue.")
    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
