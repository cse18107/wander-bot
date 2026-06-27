"""Provider-pluggable LLM/embedding construction.

Hard-coding a provider is a red flag; everything routes through here so the model
layer is config-driven and swappable. Supported: OpenAI, Google Gemini, Anthropic.
The model string defaults per-provider when left unset.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from wanderbot.config import Settings, get_settings

CHAT_DEFAULTS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "anthropic": "claude-3-5-sonnet-latest",
}

EMBED_DEFAULTS: dict[str, str] = {
    "openai": "text-embedding-3-small",
    "gemini": "models/text-embedding-004",
}


def _chat_model_name(settings: Settings, override: str | None) -> str:
    return override or settings.llm_model or CHAT_DEFAULTS[settings.llm_provider]


def build_chat_model(
    settings: Settings | None = None,
    *,
    temperature: float = 0.2,
    model: str | None = None,
) -> BaseChatModel:
    settings = settings or get_settings()
    provider = settings.llm_provider
    model_name = _chat_model_name(settings, model)

    if provider == "openai":
        if settings.openai_api_key is None:
            raise RuntimeError("WB_OPENAI_API_KEY is required for the openai provider")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=settings.openai_api_key.get_secret_value(),
        )

    if provider == "gemini":
        if settings.google_api_key is None:
            raise RuntimeError("WB_GOOGLE_API_KEY is required for the gemini provider")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=settings.google_api_key.get_secret_value(),
        )

    if provider == "anthropic":  # pragma: no cover - illustrative swap point
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_name, temperature=temperature)

    raise ValueError(f"Unsupported llm_provider: {provider}")


@lru_cache(maxsize=1)
def build_embeddings(settings: Settings | None = None) -> Embeddings:
    settings = settings or get_settings()
    provider = settings.llm_provider
    model_name = settings.embedding_model or EMBED_DEFAULTS.get(provider, "")

    if provider == "openai":
        if settings.openai_api_key is None:
            raise RuntimeError("WB_OPENAI_API_KEY is required for embeddings")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model_name,
            api_key=settings.openai_api_key.get_secret_value(),
        )

    if provider == "gemini":
        if settings.google_api_key is None:
            raise RuntimeError("WB_GOOGLE_API_KEY is required for embeddings")
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=model_name,
            google_api_key=settings.google_api_key.get_secret_value(),
        )

    raise ValueError(f"No embedding backend for provider: {provider}")
