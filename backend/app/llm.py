import hashlib
import os
from typing import Callable

import httpx

DEFAULT_MODEL = "gemini-2.5-flash"
TIMEOUT = 60.0
_cache: dict[str, str] = {}


class PlanError(RuntimeError):
    pass


def provider() -> str:
    """'gemini' when a key is set, otherwise 'template' (built-in writer, no AI)."""
    return "gemini" if os.getenv("GEMINI_API_KEY") else "template"


def model() -> str | None:
    return (os.getenv("LLM_MODEL") or DEFAULT_MODEL) if provider() == "gemini" else None


def is_mock() -> bool:
    """True when no AI is in use (built-in writer only)."""
    return provider() == "template"


def _gemini(prompt: str) -> str:
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model()}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        # Gemini 2.5+ models before answering and that counts towards maxOutputTokens,
        # so leave plenty of room or the plan gets cut off.
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 8192}},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))

# kept as a lookup so tests can swap in a fake Gemini
PROVIDERS = {"gemini": _gemini}  


def generate(prompt: str, fallback: Callable[[str], str]) -> tuple[str, dict]:
    """Returns (text, info). info = {"provider", "model", "cached", "fallback", "error"?}.
    `fallback(note)` writes a plan without AI; note explains why ('' when no key is set)."""
    p = provider()
    info = {"provider": p, "model": model(), "cached": False, "fallback": False}
    if p == "template":
        return fallback(""), info

    key = hashlib.sha256(f"{model()}|{prompt}".encode()).hexdigest()
    if key in _cache:
        return _cache[key], {**info, "cached": True}
    try:
        text = PROVIDERS["gemini"](prompt).strip()
        if not text:
            raise ValueError("empty reply")
    except Exception as e:  # network error, free-tier limit, bad key, empty reply
        reason = "free-tier limit reached" if "429" in str(e) else type(e).__name__
        note = f"Gemini was unavailable ({reason}), so this plan was written directly from the analysis."
        return fallback(note), {**info, "fallback": True, "error": reason}
    _cache[key] = text
    return text, info