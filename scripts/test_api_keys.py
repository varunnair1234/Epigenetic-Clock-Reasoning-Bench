"""Smoke-test the three model APIs configured in .env.

Sends a single ~5-token "respond with OK" prompt to each provider and reports
PASS/FAIL.  Keys are loaded from .env and never printed back.

Run from the repo root:
    python scripts/test_api_keys.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ---------- .env loading (no dependency on python-dotenv) ----------

def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def mask(s: str | None, keep: int = 4) -> str:
    if not s:
        return "<empty>"
    if len(s) <= keep * 2:
        return "*" * len(s)
    return f"{s[:keep]}…{s[-keep:]}"


# ---------- HTTP helper ----------

def post_json(url: str, headers: dict[str, str], body: dict, timeout: float = 30.0) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return -1, f"URL error: {e.reason}"
    except Exception as e:
        return -2, f"{type(e).__name__}: {e}"


# ---------- Per-provider tests ----------

def test_claude(api_key: str) -> tuple[bool, str]:
    if not api_key or api_key == "XXX":
        return False, "ANTHROPIC_API_KEY missing or still XXX"
    status, body = post_json(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body={
            "model": "claude-sonnet-4-5",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        },
    )
    if status == 200:
        data = json.loads(body)
        text = data.get("content", [{}])[0].get("text", "").strip()
        return True, f"reply={text!r}  model={data.get('model')}"
    return False, f"HTTP {status}  body[:200]={body[:200]!r}"


def test_gemini(api_key: str) -> tuple[bool, str]:
    if not api_key or api_key == "XXX":
        return False, "GOOGLE_API_KEY missing or still XXX"
    model = "gemini-2.5-flash-lite"  # Lowest tier, separate quota bucket
    status, body = post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        headers={"content-type": "application/json"},
        body={
            "contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
            "generationConfig": {
                "maxOutputTokens": 16,
                "temperature": 0.0,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
    )
    if status == 200:
        data = json.loads(body)
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            text = "<no text in response>"
        return True, f"reply={text!r}  model={model}"
    return False, f"HTTP {status}  body[:200]={body[:200]!r}"


def test_biollm(token: str, endpoint: str) -> tuple[bool, str]:
    if not token or token == "XXX":
        return False, "HF_TOKEN missing or still XXX"
    if not endpoint:
        return False, "BIOLLM_ENDPOINT missing"
    status, body = post_json(
        endpoint.rstrip("/") + "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        body={
            "model": "longevity-llm",
            "max_tokens": 16,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=120.0,  # endpoint can cold-start
    )
    if status == 200:
        data = json.loads(body)
        try:
            text = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            text = "<no text>"
        return True, f"reply={text!r}  model={data.get('model','longevity-llm')}"
    return False, f"HTTP {status}  body[:200]={body[:200]!r}"


# ---------- Main ----------

def main() -> int:
    env = load_env(Path(".env"))
    # also fall back to process env for CI
    for k in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "HF_TOKEN", "BIOLLM_ENDPOINT"):
        env.setdefault(k, os.environ.get(k, ""))

    print(f"{'=' * 70}")
    print("API key smoke test")
    print(f"{'=' * 70}")
    print(f"  ANTHROPIC_API_KEY = {mask(env.get('ANTHROPIC_API_KEY'))}")
    print(f"  GOOGLE_API_KEY    = {mask(env.get('GOOGLE_API_KEY'))}")
    print(f"  HF_TOKEN          = {mask(env.get('HF_TOKEN'))}")
    print(f"  BIOLLM_ENDPOINT   = {env.get('BIOLLM_ENDPOINT', '<unset>')}")
    print()

    results = []
    for name, fn in [
        ("Claude (Anthropic)", lambda: test_claude(env.get("ANTHROPIC_API_KEY", ""))),
        ("Gemini (Google)",    lambda: test_gemini(env.get("GOOGLE_API_KEY", ""))),
        ("BioLLM (HF endpoint)", lambda: test_biollm(env.get("HF_TOKEN", ""),
                                                     env.get("BIOLLM_ENDPOINT", ""))),
    ]:
        ok, detail = fn()
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}")
        print(f"         {detail}")
        results.append((name, ok))
        print()

    n_pass = sum(1 for _, ok in results if ok)
    print(f"{'=' * 70}")
    print(f"{n_pass}/{len(results)} providers reachable")
    print(f"{'=' * 70}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
