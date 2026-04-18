from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from ludomancer.llm.base import SYSTEM_PROMPT, LLMClientError, recommend_with_one_retry
from ludomancer.models import LLMPayload, LLMRecommendationResponse


def _extract_text_from_anthropic_response(response: Any) -> str:
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")

    if isinstance(content, str):
        text = content.strip()
        if text:
            return text

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text)

        merged = "\n".join(parts).strip()
        if merged:
            return merged

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    raise ValueError("Anthropic response did not include text content.")


class AnthropicLLMClient:
    """LLM provider implementation backed by Anthropic's Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float = 15.0,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._client = client or Anthropic(api_key=api_key, timeout=timeout_s)
        self._owns_client = client is None

    def recommend(self, payload: LLMPayload) -> LLMRecommendationResponse:
        return recommend_with_one_retry(payload, self._invoke)

    def _invoke(self, messages: list[dict[str, str]]) -> str:
        anthropic_messages = [
            {"role": message["role"], "content": message["content"]} for message in messages
        ]
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1200,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=anthropic_messages,
            )
        except Exception as error:  # pragma: no cover - exercised via provider-specific failures
            raise LLMClientError("Anthropic request failed.") from error

        return _extract_text_from_anthropic_response(response)

    def close(self) -> None:
        if not self._owns_client:
            return
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
