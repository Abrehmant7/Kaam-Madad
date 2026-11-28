"""Groq chat-completions client with strict JSON Schema output (interpretation and agreement check).

Contract (Groq docs, checked Nov 2026): POST {GROQ_API_BASE}/chat/completions with
``Authorization: Bearer <GROQ_API_KEY>``; body ``{"model", "messages", "response_format": {"type":
"json_schema", "json_schema": {"name", "strict": true, "schema"}}, "reasoning_effort",
"include_reasoning", "max_completion_tokens"}``. ``openai/gpt-oss-120b`` supports strict mode, which
requires every property to be listed in ``required`` and ``additionalProperties: false`` on every object
(``strict_schema`` adds both; nullable values use ``["string", "null"]``). The answer is
``choices[0].message.content``; gpt-oss reasoning is a separate field and is not requested.

Model output is still untrusted: it is parsed as JSON here and validated by the caller with the app's own
rules (``apps.voice.drafts`` / ``apps.providers.agreement.verify_findings``) before anything is used.
Errors map to the shared taxonomy; 429 and 498 (capacity) are usage limits; no provider text is echoed.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import httpx
from django.conf import settings

from . import http
from .errors import ProviderError, ProviderInvalidOutput, ProviderLimitReached, ProviderNotConfigured, ProviderUnavailable

PROVIDER = "groq"
REASONING_EFFORTS = ("low", "medium", "high")


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``schema`` that satisfies strict mode: all properties required, no extra properties."""
    result = copy.deepcopy(schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                properties = node.get("properties", {})
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


def classify_error(response: httpx.Response) -> ProviderError | None:
    status = response.status_code
    if status == 498:  # flex tier capacity exceeded: a usage limit, try again later
        return ProviderLimitReached("capacity_exceeded", retry_after_seconds=http.retry_after(response))
    if status == 413:
        return ProviderUnavailable("request_too_large")
    if status in (400, 422):
        try:
            error = response.json().get("error") or {}
        except (ValueError, AttributeError):
            error = {}
        code = error.get("code") if isinstance(error, dict) else None
        message = (error.get("message") or "") if isinstance(error, dict) else ""
        if code == "json_validate_failed" or "schema" in str(message).lower() or status == 422:
            return ProviderInvalidOutput("schema_validation_failed")
        if code == "model_not_found" or code == "model_decommissioned":
            return ProviderNotConfigured("model_not_available")
    if status == 404:
        return ProviderNotConfigured("model_not_available")
    return None


class GroqClient:
    def __init__(self, *, model: str, reasoning_effort: str, client: httpx.Client | None = None):
        if not settings.GROQ_API_KEY:
            raise ProviderNotConfigured("missing_api_key")
        if not model:
            raise ProviderNotConfigured("missing_model")
        if reasoning_effort not in REASONING_EFFORTS:
            raise ProviderNotConfigured("invalid_reasoning_effort")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.client = client or http.default_client()
        self.url = f"{settings.GROQ_API_BASE.rstrip('/')}/chat/completions"

    def generate_json(
        self, *, system_instruction: str, user_content: str, schema: dict[str, Any], schema_name: str,
        max_completion_tokens: int | None = None, reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": strict_schema(schema)},
            },
            "reasoning_effort": reasoning_effort or self.reasoning_effort,
            "temperature": settings.GROQ_TEMPERATURE,
            "include_reasoning": False,
            "max_completion_tokens": max_completion_tokens or settings.GROQ_MAX_COMPLETION_TOKENS,
        }
        response = http.post(
            self.client, self.url, provider=PROVIDER,
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json",
                     "User-Agent": "kaam-madad"},
            json=body, classify_error=classify_error,
        )
        try:
            data = response.json()
        except ValueError:
            raise ProviderInvalidOutput("response_not_json") from None
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderInvalidOutput("no_text_output") from None
        if choice.get("finish_reason") == "length":
            raise ProviderInvalidOutput("output_truncated")
        if not isinstance(content, str) or not content.strip():
            raise ProviderInvalidOutput("no_text_output")
        try:
            parsed = json.loads(content)
        except ValueError:
            raise ProviderInvalidOutput("output_not_json") from None
        if not isinstance(parsed, dict):
            raise ProviderInvalidOutput("output_not_object")
        return parsed
