"""Shared configuration for the existing chat generation gateway."""

import os
from urllib.parse import urlsplit

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider


class AgentConfigurationError(ValueError):
    """Required model configuration is missing or invalid."""


def _validate_gateway(gateway: str) -> None:
    try:
        parsed = urlsplit(gateway)
        _ = parsed.port  # Access validates malformed or out-of-range ports.
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("An HTTP(S) gateway host is required.")
    except ValueError:
        raise AgentConfigurationError(
            "Model gateway configuration is invalid."
        ) from None


def configured_chat_model(
    *, max_retries: int | None = None
) -> tuple[OpenAIChatModel, OpenAIChatModelSettings | None]:
    names = ("LLM_API_TOKEN", "LLM_API_GATEWAY", "LLM_MODEL")
    values = [os.environ.get(name, "").strip() for name in names]
    if not all(values):
        raise AgentConfigurationError("Model configuration is incomplete.")
    token, gateway, model_name = values
    _validate_gateway(gateway)
    if max_retries is None:
        provider = OpenAIProvider(base_url=gateway, api_key=token)
    else:
        provider = OpenAIProvider(
            openai_client=AsyncOpenAI(
                base_url=gateway, api_key=token, max_retries=max_retries
            )
        )
    settings = (
        OpenAIChatModelSettings(openai_reasoning_effort="none")
        if model_name == "gpt-6-luna"
        else None
    )
    return OpenAIChatModel(model_name, provider=provider), settings
