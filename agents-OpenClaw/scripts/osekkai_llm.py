"""Server-only, provider-neutral LLM adapter for Osekkai conversation tasks."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests


class LLMError(RuntimeError):
    """A bounded provider failure that must fall back to deterministic copy."""

    def __init__(self, code: str, message: str = "LLM provider unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    model: str
    api_key: str
    base_url: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "LLMConfig":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        raw_enabled = os.environ.get("OSEKKAI_LLM_ENABLED", "").strip().casefold()
        enabled = bool(api_key) and raw_enabled not in {"0", "false", "no", "off", "disabled"}
        provider = os.environ.get("OSEKKAI_LLM_PROVIDER", "openai").strip().casefold() or "openai"
        model = os.environ.get("OSEKKAI_LLM_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini"
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        try:
            timeout_seconds = float(os.environ.get("OSEKKAI_LLM_TIMEOUT_SECONDS", "7"))
        except ValueError:
            timeout_seconds = 7.0
        timeout_seconds = min(20.0, max(1.0, timeout_seconds))
        return cls(
            enabled=enabled,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )


def _extract_output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "refusal":
                raise LLMError("LLM_REFUSAL")
            text = content.get("text")
            if content.get("type") == "output_text" and isinstance(text, str):
                chunks.append(text)
    value = "".join(chunks).strip()
    if not value:
        raise LLMError("LLM_EMPTY_OUTPUT")
    return value


class LLMClient:
    """Small adapter around the OpenAI Responses API with strict JSON output."""

    RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}

    def __init__(self, config: LLMConfig | None = None, session: requests.Session | None = None):
        self.config = config or LLMConfig.from_env()
        self.session = session or requests.Session()

    @property
    def available(self) -> bool:
        return self.config.enabled and self.config.provider == "openai" and bool(self.config.api_key)

    def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        schema_name: str,
        schema: dict[str, Any],
        max_output_tokens: int = 900,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not self.available:
            raise LLMError("LLM_DISABLED")
        if self.config.provider != "openai":
            raise LLMError("LLM_PROVIDER_UNSUPPORTED")
        if not 1 <= max_output_tokens <= 4000:
            raise LLMError("LLM_OUTPUT_LIMIT_INVALID")

        payload = {
            "model": self.config.model,
            "store": False,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "X-Client-Request-Id": str(uuid.uuid4()),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:128]

        last_error: LLMError | None = None
        for attempt in range(2):
            try:
                response = self.session.post(
                    f"{self.config.base_url}/responses",
                    headers=headers,
                    json=payload,
                    timeout=(3.05, self.config.timeout_seconds),
                )
            except requests.Timeout as exc:
                last_error = LLMError("LLM_TIMEOUT")
                if attempt == 0:
                    continue
                raise last_error from exc
            except requests.RequestException as exc:
                raise LLMError("LLM_TRANSPORT_ERROR") from exc

            if response.status_code in self.RETRYABLE_STATUS:
                last_error = LLMError(
                    "LLM_QUOTA" if response.status_code == 429 else "LLM_PROVIDER_UNAVAILABLE"
                )
                if attempt == 0:
                    time.sleep(0.15)
                    continue
                raise last_error
            if not response.ok:
                raise LLMError("LLM_AUTH" if response.status_code in {401, 403} else "LLM_REQUEST_REJECTED")
            try:
                response_body = response.json()
            except ValueError as exc:
                raise LLMError("LLM_MALFORMED_RESPONSE") from exc
            if not isinstance(response_body, dict):
                raise LLMError("LLM_MALFORMED_RESPONSE")
            status = response_body.get("status")
            if status not in {None, "completed"}:
                raise LLMError("LLM_INCOMPLETE")
            output_text = _extract_output_text(response_body)
            try:
                value = json.loads(output_text)
            except json.JSONDecodeError as exc:
                raise LLMError("LLM_MALFORMED_JSON") from exc
            if not isinstance(value, dict):
                raise LLMError("LLM_MALFORMED_JSON")
            return value

        raise last_error or LLMError("LLM_PROVIDER_UNAVAILABLE")
