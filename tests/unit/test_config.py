from wanderbot.config import Settings


def test_amadeus_base_url_switches_by_env() -> None:
    test_settings = Settings(amadeus_env="test")
    prod_settings = Settings(amadeus_env="production")
    assert test_settings.amadeus_base_url == "https://test.api.amadeus.com"
    assert prod_settings.amadeus_base_url == "https://api.amadeus.com"


def test_defaults_are_local_and_safe() -> None:
    s = Settings(_env_file=None)
    assert s.env == "local"
    assert s.is_production is False
    assert s.max_graph_iterations > 0


def test_blank_secrets_become_none() -> None:
    s = Settings(_env_file=None, tavily_api_key="", amadeus_client_id="  ", bedrock_guardrail_id="")
    assert s.tavily_api_key is None
    assert s.amadeus_client_id is None
    assert s.bedrock_guardrail_id is None
    # blank guardrail id in auto mode -> Bedrock disabled (uses regex)
    assert s.bedrock_guardrails_enabled is False
