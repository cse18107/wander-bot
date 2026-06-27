import httpx
import pytest
import respx

from wanderbot.config import Settings
from wanderbot.providers.amadeus.token_manager import AmadeusTokenManager


@pytest.mark.asyncio
@respx.mock
async def test_token_is_cached_and_reused() -> None:
    settings = Settings(
        amadeus_client_id="id", amadeus_client_secret="secret", amadeus_env="test"
    )
    route = respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    async with httpx.AsyncClient() as client:
        mgr = AmadeusTokenManager(settings, client=client)
        t1 = await mgr.get_token()
        t2 = await mgr.get_token()

    assert t1 == t2 == "tok-123"
    assert route.call_count == 1  # second call served from cache
