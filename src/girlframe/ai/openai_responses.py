"""Shared bounded OpenAI Responses transport for structured, tool-free proposals."""

import json
import os
from http.client import HTTPException, HTTPSConnection
from typing import Any

from girlframe.ai.provider import MAX_OUTPUT_TOKENS, ProviderError, ProviderUsage


class ResponseText(ProviderUsage):
    text: str


def request_text(
    model: str,
    request_id: str,
    instructions: str,
    data: dict[str, Any],
    output_format: dict[str, Any],
) -> ResponseText:
    credential = os.environ.get("OPENAI_API_KEY", "").strip()
    if not credential:
        raise ProviderError("provider_unavailable")
    body = json.dumps(
        {
            "model": model,
            "instructions": instructions,
            "input": json.dumps(data),
            "text": {"format": output_format},
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "store": False,
            "tools": [],
            "truncation": "disabled",
        }
    )
    connection = HTTPSConnection("api.openai.com", timeout=20)
    try:
        connection.request(
            "POST",
            "/v1/responses",
            body=body.encode(),
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
                "X-Client-Request-Id": request_id,
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ProviderError("provider_unavailable")
        raw = response.read(65537)
    except (HTTPException, OSError, ValueError):
        raise ProviderError("provider_unavailable") from None
    finally:
        connection.close()
    if len(raw) > 65536:
        raise ProviderError("invalid_proposal")
    try:
        return _parse(json.loads(raw))
    except (KeyError, TypeError, ValueError):
        raise ProviderError("invalid_proposal") from None


def _parse(document: Any) -> ResponseText:
    if not isinstance(document, dict) or document["status"] != "completed":
        raise ProviderError("invalid_proposal")
    messages = []
    for item in document["output"]:
        if item["type"] == "reasoning":
            continue
        if (
            item["type"] != "message"
            or item["role"] != "assistant"
            or item["status"] != "completed"
        ):
            raise ProviderError("invalid_proposal")
        for part in item["content"]:
            if part["type"] != "output_text":
                raise ProviderError("invalid_proposal")
            messages.append(part["text"])
    if len(messages) != 1:
        raise ProviderError("invalid_proposal")
    return ResponseText(
        text=messages[0],
        trace_id=document["id"],
        model=document["model"],
        input_tokens=document["usage"]["input_tokens"],
        output_tokens=document["usage"]["output_tokens"],
    )
