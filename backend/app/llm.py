"""Claude API call that writes the restoration plan.

- No ANTHROPIC_API_KEY: returns clearly-labelled MOCK output (no API spend while building).
- Identical requests are cached in memory, so repeated demo clicks cost nothing.
- API failures raise PlanError, which the API turns into a clear 502 message.
"""
import hashlib
import json
import os

PLAN_PROMPT = """Write a one-page coastal ecosystem restoration plan for {area}, Fiji, to reduce
cyclone damage. Audience: city council, town planners and community leaders.
Use ONLY the facts in the JSON below; do not invent numbers, names, costs or species.
Plain language, short sentences. Name the ecosystem types exactly as given in the facts.

Structure (Markdown):
# Restoring {area}'s coast to reduce cyclone damage
## What we found
## Where to restore first (and why)
## What restoration protects
## How long it takes and what else is needed
## Limits of this analysis

In "How long it takes", use the maturity times in the facts and say that restored ecosystems
take years to decades to reach full protective value, so restoration should be combined with
nearer-term measures (cyclone-resistant housing, safe shelters, setbacks from the shore).
In "Limits", say results come from a simplified, conservative model based on published field
ranges, that storm-surge reduction is small, and that the plan must be reviewed with local
communities, landowners, ecologists and the relevant Fiji government agencies before any
decision. Restoration should be community-led.

Facts:
{facts}"""

_cache: dict[str, str] = {}


class PlanError(RuntimeError):
    pass


def is_mock() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def _model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


def _key(area: str, summary: dict) -> str:
    return hashlib.sha256(json.dumps([area, summary], sort_keys=True, default=str).encode()).hexdigest()


def write_plan(area_name: str, summary: dict) -> tuple[str, bool]:
    """Returns (markdown, cached)."""
    if is_mock():
        return (
            f"# Restoring {area_name}'s coast (MOCK)\n\n"
            "Set ANTHROPIC_API_KEY to generate a real plan.\n\n"
            f"- Ecosystem types: {', '.join(summary.get('types', ['mangrove']))}\n"
            f"- Segments selected: {len(summary.get('restored', []))}\n"
            f"- Hectares to restore: {summary.get('hectares', '?')}\n"
            f"- People better protected: {summary.get('people_better_protected', '?')}\n"
        ), False

    key = _key(area_name, summary)
    if key in _cache:
        return _cache[key], True

    import anthropic

    try:
        client = anthropic.Anthropic(timeout=60.0, max_retries=2)
        msg = client.messages.create(
            model=_model(),
            max_tokens=1500,
            messages=[{"role": "user", "content": PLAN_PROMPT.format(
                area=area_name, facts=json.dumps(summary, indent=1, default=str))}],
        )
    except anthropic.APIError as e:
        raise PlanError(f"The AI service could not write the plan right now ({type(e).__name__}). Try again shortly.") from e

    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if not text:
        raise PlanError("The AI service returned an empty plan. Try again.")
    _cache[key] = text
    return text, False