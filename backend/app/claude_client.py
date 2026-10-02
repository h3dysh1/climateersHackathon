"""Claude API call that writes the restoration plan.

With no ANTHROPIC_API_KEY set, returns clearly-labelled MOCK output so the team can
build the UI without spending API credits.
"""
import json
import os

PLAN_PROMPT = """Write a one-page coastal ecosystem restoration plan for {area}, Fiji, to reduce
cyclone damage. Audience: city council, town planners and community leaders.
Use ONLY the facts in the JSON below; do not invent numbers, names, costs or species.
Plain language, short sentences.

Structure (Markdown):
# Restoring {area}'s coast to reduce cyclone damage
## What we found
## Where to restore first (and why)
## What restoration protects
## How long it takes and what else is needed
## Limits of this analysis

In "How long it takes", note that mangroves take years to decades to reach full protective
value, so restoration should be combined with nearer-term measures (cyclone-resistant housing,
safe shelters, setbacks from the shore). In "Limits", say results come from a simplified,
conservative model (wave reduction from published field ranges; storm-surge reduction is small)
and must be reviewed with local communities, landowners, ecologists and the relevant Fiji
government agencies before any decision. Restoration should be community-led.

Facts:
{facts}"""


def is_mock() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def _model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


def write_plan(area_name: str, summary: dict) -> str:
    if is_mock():
        return (
            f"# Restoring {area_name}'s coast (MOCK)\n\n"
            "Set ANTHROPIC_API_KEY to generate a real plan.\n\n"
            f"- Segments selected: {len(summary.get('restored', []))}\n"
            f"- Hectares to restore: {summary.get('hectares', '?')}\n"
            f"- People better protected: {summary.get('people_better_protected', '?')}\n"
        )
    import anthropic

    msg = anthropic.Anthropic().messages.create(
        model=_model(),
        max_tokens=1500,
        messages=[{"role": "user", "content": PLAN_PROMPT.format(area=area_name, facts=json.dumps(summary, indent=1))}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
