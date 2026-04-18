from __future__ import annotations

from typing import Any

from openai import OpenAI

from ludomancer.llm.base import SYSTEM_PROMPT, LLMClientError, recommend_with_one_retry
from ludomancer.models import LLMPayload, LLMRecommendationResponse


def _extract_text_from_openrouter_response(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")

    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenRouter response did not include choices.")

    first_choice = choices[0]
    if isinstance(first_choice, dict):
        message = first_choice.get("message")
    else:
        message = getattr(first_choice, "message", None)

    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)

    if isinstance(content, str):
        text = content.strip()
        if text:
            return text

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text)
        merged = "\n".join(parts).strip()
        if merged:
            return merged

    raise ValueError("OpenRouter response did not include text content.")


class OpenRouterLLMClient:
    """LLM provider implementation backed by OpenRouter Chat Completions."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float = 15.0,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client = client or OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=timeout_s,
        )
        self._owns_client = client is None

    def recommend(self, payload: LLMPayload) -> LLMRecommendationResponse:
        return recommend_with_one_retry(payload, self._invoke)

    def _invoke(self, messages: list[dict[str, str]]) -> str:
        chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                max_tokens=1200,
                messages=chat_messages,
            )
        except Exception as error:  # pragma: no cover - exercised via provider-specific failures
            raise LLMClientError("OpenRouter request failed.") from error

        return _extract_text_from_openrouter_response(response)

    def close(self) -> None:
        if not self._owns_client:
            return
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
