"""Claude API calls: roof classification (vision) and resilience plan writing.

With no ANTHROPIC_API_KEY set, everything returns clearly-labelled MOCK output so the
team can build the UI without spending API credits.
"""
import json
import os
import random
import re

ALLOWED = {
    "roof_material": ["corrugated_iron", "concrete", "tile", "thatch", "timber", "unknown"],
    "roof_shape": ["gable", "hip", "flat", "skillion", "unknown"],
    "condition": ["good", "fair", "poor", "damaged", "unknown"],
}

CLASSIFY_PROMPT = """You are helping assess cyclone vulnerability of buildings in Fiji from a top-down aerial image tile.
Look at the building nearest the centre of the image and classify its roof.

Reply with ONLY a JSON object, no other text:
{"roof_material": one of %s,
 "roof_shape": one of %s,
 "condition": one of %s,
 "confidence": number from 0 to 1}

Use "unknown" whenever you cannot tell. Do not guess beyond what is visible.""" % (
    ALLOWED["roof_material"], ALLOWED["roof_shape"], ALLOWED["condition"])

PLAN_PROMPT = """Write a one-page cyclone resilience plan for a community meeting in {area}, Fiji.
Use ONLY the facts in the JSON below; do not invent numbers, names or costs.
Plain language, short sentences, for village leaders and a district council.

Structure (Markdown):
# Cyclone resilience plan: {area}
## What we found
## Homes to strengthen first (and why)
## What these upgrades protect
## Other protective measures to discuss
## Limits of this analysis
Note in "Limits" that results come from a simplified model checked against Cyclone Winston
survey data and must be reviewed with the community, engineers and the National Disaster
Risk Management Office before decisions are made.

Facts:
{facts}"""


def is_mock() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def _client():
    import anthropic
    return anthropic.Anthropic()


def _model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


def _clean_labels(raw: dict) -> dict:
    out = {}
    for key, allowed in ALLOWED.items():
        val = str(raw.get(key, "unknown")).strip().lower().replace(" ", "_")
        out[key] = val if val in allowed else "unknown"
    try:
        out["confidence"] = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        out["confidence"] = 0.5
    return out


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON in model reply")
    return json.loads(match.group(0))


def classify_roof(image_base64: str, media_type: str = "image/png", building_id: str = "") -> dict:
    if is_mock():
        rnd = random.Random(building_id)
        return {
            "roof_material": rnd.choice(["corrugated_iron"] * 3 + ["concrete", "timber"]),
            "roof_shape": rnd.choice(["gable", "hip", "flat"]),
            "condition": rnd.choice(["good", "fair", "poor"]),
            "confidence": 0.0,
            "mock": True,
        }
    last_err = None
    for _ in range(2):  # one retry on bad JSON
        msg = _client().messages.create(
            model=_model(),
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_base64}},
                    {"type": "text", "text": CLASSIFY_PROMPT},
                ],
            }],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            return _clean_labels(_parse_json(text))
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    return {"roof_material": "unknown", "roof_shape": "unknown", "condition": "unknown",
            "confidence": 0.0, "error": str(last_err)}


def write_plan(area_name: str, summary: dict) -> str:
    if is_mock():
        before, after = summary.get("before", {}), summary.get("after", {})
        return (
            f"# Cyclone resilience plan: {area_name} (MOCK)\n\n"
            f"Set ANTHROPIC_API_KEY to generate a real plan.\n\n"
            f"- High-risk buildings before upgrades: {before.get('high', '?')}\n"
            f"- High-risk buildings after upgrades: {after.get('high', '?')}\n"
            f"- Homes upgraded: {len(summary.get('upgraded', []))}\n"
        )
    msg = _client().messages.create(
        model=_model(),
        max_tokens=1500,
        messages=[{"role": "user", "content": PLAN_PROMPT.format(area=area_name, facts=json.dumps(summary, indent=1))}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
