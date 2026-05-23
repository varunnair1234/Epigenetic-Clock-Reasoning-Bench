"""Model adapters for the eval harness.

Three providers, one contract: each client exposes ``complete(prompt) -> str``
returning the model's raw text response. Authentication keys come from
environment variables (loaded from .env by ``run_eval.py``).

If a call fails, the client raises ``ClientError`` with a short, masked
message — no API keys ever leak into logs.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol


class ClientError(RuntimeError):
    """Raised when a model call fails. Message is safe to log."""


def _post_json(url: str, headers: dict[str, str], body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:300]
        raise ClientError(f"HTTP {e.code}: {body_text}") from e
    except urllib.error.URLError as e:
        raise ClientError(f"URL error: {e.reason}") from e
    except (TimeoutError, OSError) as e:
        raise ClientError(f"network error: {type(e).__name__}: {e}") from e


class Client(Protocol):
    name: str
    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.0) -> str: ...


# ---------- Anthropic / Claude ----------

class ClaudeClient:
    name = "claude"
    model = "claude-sonnet-4-6"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key or self.api_key == "XXX":
            raise ClientError("ANTHROPIC_API_KEY not set")

    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.0) -> str:
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            body={
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        return "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")


# ---------- Google / Gemini ----------

class GeminiClient:
    name = "gemini"
    # Fallback chain: try models in order until one succeeds
    models = ["gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-2.0-flash-lite"]

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not self.api_key or self.api_key == "XXX":
            raise ClientError("GOOGLE_API_KEY not set")

    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.0) -> str:
        last_error = None
        for model in self.models:
            try:
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/"
                    f"models/{model}:generateContent?key={self.api_key}"
                )
                data = _post_json(
                    url,
                    headers={"content-type": "application/json"},
                    body={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "maxOutputTokens": max_tokens,
                            "temperature": temperature,
                            # Gemini 2.5 otherwise burns most of max_tokens on
                            # internal "thinking" before producing visible output.
                            "thinkingConfig": {"thinkingBudget": 0},
                        },
                    },
                    timeout=60.0,
                )
                parts = data["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts if "text" in p)
            except (ClientError, KeyError, IndexError) as e:
                last_error = e
                continue  # Try next model in fallback chain

        # All models failed
        raise ClientError(f"All Gemini models failed. Last error: {last_error}")


# ---------- HuggingFace Inference Endpoint / BioLLM ----------

class BioLLMClient:
    name = "biollm"
    model = "longevity-llm"

    def __init__(self, token: str | None = None, endpoint: str | None = None):
        self.token = token or os.environ.get("HF_TOKEN", "")
        self.endpoint = endpoint or os.environ.get("BIOLLM_ENDPOINT", "")
        if not self.token or self.token == "XXX":
            raise ClientError("HF_TOKEN not set")
        if not self.endpoint:
            raise ClientError("BIOLLM_ENDPOINT not set")

    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.0) -> str:
        data = _post_json(
            self.endpoint.rstrip("/") + "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body={
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=180.0,  # endpoint may cold-start
        )
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            return ""


def build_clients() -> dict[str, Client]:
    return {
        "claude": ClaudeClient(),
        "gemini": GeminiClient(),
        "biollm": BioLLMClient(),
    }
