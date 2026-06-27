import pytest

from wanderbot.config import Settings
from wanderbot.llm_factory import (
    CHAT_DEFAULTS,
    EMBED_DEFAULTS,
    _chat_model_name,
    build_chat_model,
)


def _settings(**kw):
    # _env_file=None so the test ignores any real .env on disk.
    return Settings(_env_file=None, llm_model=None, **kw)


def test_provider_defaults_resolve_per_provider() -> None:
    assert _chat_model_name(_settings(llm_provider="openai"), None) == "gpt-4o-mini"
    assert _chat_model_name(_settings(llm_provider="gemini"), None) == "gemini-1.5-flash"
    # explicit model wins
    assert _chat_model_name(_settings(llm_provider="gemini"), "gemini-1.5-pro") == "gemini-1.5-pro"
    # configured settings model wins over default
    assert _chat_model_name(Settings(_env_file=None, llm_provider="gemini", llm_model="gemini-2.0-flash"), None) == "gemini-2.0-flash"


def test_gemini_is_a_supported_provider() -> None:
    assert "gemini" in CHAT_DEFAULTS
    assert "gemini" in EMBED_DEFAULTS
    Settings(llm_provider="gemini")  # accepted by the Literal


def test_missing_keys_raise_clear_errors() -> None:
    with pytest.raises(RuntimeError, match="WB_OPENAI_API_KEY"):
        build_chat_model(Settings(llm_provider="openai", openai_api_key=None))
    with pytest.raises(RuntimeError, match="WB_GOOGLE_API_KEY"):
        build_chat_model(Settings(llm_provider="gemini", google_api_key=None))
