"""Google Gemini API client (Interactions API) used for speech-to-text and interpretation.

Contract per the Gemini API docs (checked Nov 2026, https://ai.google.dev/gemini-api/docs/ →
aistudio.google.com/docs): POST {base}/interactions with header ``x-goog-api-key``;
body ``{"model", "input": [parts], "system_instruction", "response_format":
{"type": "text", "mime_type": "application/json", "schema": {...}}, "generation_config":
{"max_output_tokens"}, "store": false}``. Audio parts are ``{"type": "audio", "data":
<base64>, "mime_type": "audio/wav"}`` (inline requests up to 20 MB in total).

``store: false`` opts out of server-side storage of the interaction (privacy: we do
not need multi-turn state). Gemini 4 / 3.6+ ignore temperature, so none is sent.

The documented SDK field for the answer is ``output_text``; the raw REST shape is
documented via ``steps[]`` where ``type == "model_output"`` and ``content[]`` holds
text items. Both are accepted below. Model output is always parsed as JSON and then
validated by the caller — it is never trusted.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from django.conf import settings

from . import http
from .errors import ProviderInvalidOutput, ProviderNotConfigured

PROVIDER = "gemini"


def extract_output_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    steps = data.get("steps")
    if isinstance(steps, list):
        for step in reversed(steps):
            if isinstance(step, dict) and step.get("type") == "model_output":
                texts = [
                    item.get("text")
                    for item in step.get("content") or []
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
                ]
                if texts:
                    return "".join(texts)
    outputs = data.get("outputs")
    if isinstance(outputs, list):
        texts = [o.get("text") for o in outputs if isinstance(o, dict) and isinstance(o.get("text"), str)]
        if texts:
            return "".join(texts)
    return None


class GeminiClient:
    def __init__(self, *, model: str, client: httpx.Client | None = None, api_key: str | None = None):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        if not self.api_key:
            raise ProviderNotConfigured("missing_api_key")
        self.model = model
        self.client = client or http.default_client()
        self.base_url = settings.GEMINI_API_BASE.rstrip("/")

    def generate_json(
        self,
        *,
        system_instruction: str,
        parts: list[dict[str, Any]],
        schema: dict[str, Any],
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "input": parts,
            "system_instruction": system_instruction,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
            "generation_config": {"max_output_tokens": max_output_tokens},
            "store": False,
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        if settings.GEMINI_API_REVISION:
            headers["Api-Revision"] = settings.GEMINI_API_REVISION
        response = http.post(self.client, f"{self.base_url}/interactions", provider=PROVIDER, headers=headers, json=body)
        try:
            data = response.json()
        except ValueError:
            raise ProviderInvalidOutput("response_not_json") from None
        text = extract_output_text(data)
        if text is None:
            raise ProviderInvalidOutput("no_text_output")
        try:
            parsed = json.loads(text)
        except ValueError:
            raise ProviderInvalidOutput("output_not_json") from None
        if not isinstance(parsed, dict):
            raise ProviderInvalidOutput("output_not_object")
        return parsed
