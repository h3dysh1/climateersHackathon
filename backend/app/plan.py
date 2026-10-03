"""The flood plan: the prompt sent to the AI, and a built-in writer used when there's no AI."""
import json

from . import flood, llm

PROMPT = """Write a one-page flood resilience plan for {area}{where}, for {flood_type}.
Flood levels are metres the river rises above its normal level.
Audience: town council, planners and community leaders. Plain language, short sentences.
Use ONLY the facts in the JSON below; do not invent numbers, places, costs or names.

Structure (Markdown):
# Flood resilience plan: {area}
## What we found
## What the tested measures achieve
## Recommended priorities
## How this fits with existing work
## Limits of this analysis

In "How this fits", say the plan should support, not replace, official flood work in the area
(the "place" facts list existing work) and early warning. In "Limits", say this is a
simplified planning model based on each place's height above the nearest river (HAND) that does not simulate river flow or rainfall, that
measure effects marked as assumptions are what-ifs, and that decisions must be made with
communities, engineers and the relevant government agencies (named in the place facts if given).
Any flood reduction from dredging or riverbank vegetation is the user's assumption: say so. Dredging benefits
fade as silt returns; vegetation helps most in smaller floods but has co-benefits (less erosion and silt,
habitat, carbon). Do not overstate either.

Facts:
{facts}"""


def _n(x):
    return int(x) if isinstance(x, float) and x.is_integer() else x


def template_plan(area: str, s: dict, note: str = "", place: dict | None = None) -> str:
    """A plain-language plan written directly from the numbers. No AI, no cost."""
    base, after, saved = s.get("baseline", {}), s.get("with_measures", {}), s.get("saved", {})
    m = s.get("measures", {})
    lines = [f"# Flood resilience plan: {area}", ""]
    if note:
        lines += [f"_{note}_", ""]
    lines += ["## What we found", ""]
    if base:
        lines.append(f"When the river rises **{_n(base.get('level_m'))} m** above its normal level:")
        lines.append(f"- **{base.get('people_water_inside', '?')} people** live in homes where water gets inside "
                     f"({base.get('buildings_water_inside', '?')} buildings).")
        lines.append(f"- {base.get('buildings_reached', '?')} buildings are reached by floodwater.")
        if base.get("facilities_flooded"):
            names = ", ".join(f.get("name") or f["id"] for f in base["facilities_flooded"][:6])
            lines.append(f"- Critical facilities flooded: {names}.")
        if base.get("roads_cut"):
            lines.append(f"- {len(base['roads_cut'])} road sections ({base.get('roads_cut_km', '?')} km) become impassable.")
    lines += ["", "## What the tested measures achieve", ""]
    if not m:
        lines.append("No measures tested yet. Try river channel clearing, riverbank vegetation or raising homes in the app.")
    else:
        if m.get("raise_homes"):
            r = m["raise_homes"]
            lines.append(f"- Raising {len(after.get('homes_raised', [])) or r.get('count')} homes by "
                         f"{r.get('height_m', flood.MEASURES['raise_homes']['default_height_m'])} m, "
                         "chosen where raising keeps water out.")
        if m.get("channel_clearing_m"):
            lines.append(f"- What-if: dredging/desilting the river lowers floods by {m['channel_clearing_m']} m "
                         "(an assumption; the benefit fades as silt returns).")
        if m.get("nature_based"):
            lines.append(f"- What-if: riverbank vegetation buffers lower floods by "
                         f"{m['nature_based'].get('reduction_pct', flood.MEASURES['nature_based']['default_reduction_pct'])}% "
                         "(an assumption; the effect fades in very big floods).")
        lines.append("")
        lines.append(f"Together these keep water out of the homes of **{saved.get('people_kept_dry_inside', '?')} people** "
                     f"({saved.get('homes_kept_dry_inside', '?')} homes), protect {saved.get('facilities_protected', 0)} facilities "
                     f"and reopen {saved.get('roads_reopened', 0)} road sections.")
        if after:
            lines.append(f"People with water inside fall from {base.get('people_water_inside', '?')} to {after.get('people_water_inside', '?')}.")
    lines += ["", "## Recommended priorities", "",
              "1. Raise homes in the worst-hit areas where a modest lift keeps water out; they protect people every flood season.",
              f"2. Homes in deeper water ({base.get('homes_too_deep_to_raise', '?')} at this level) need other options, "
              "such as relocation to higher ground, decided with the families affected.",
              "3. Plant and protect riverbank vegetation and wetlands: it reduces erosion and the silt that makes "
              "dredging necessary, and helps most in smaller floods.",
              "4. Treat dredging as a repeated maintenance cost, not a one-off fix, since silt returns.",
              "5. Move or flood-proof any clinic, school or power substation inside the flood zone, and link this plan "
              "to flood early warnings.",
              "", "## How this fits with existing work", "",
              "This plan should support, not replace, official flood work in the area"
              + (f", such as: {'; '.join(place['existing_work'])}" if place and place.get("existing_work") else "")
              + ", and flood early warning.",
              "", "## Limits of this analysis", "",
              "- This is a simplified planning model based on height above the nearest river (HAND). It does not simulate river flow, rainfall or timing.",
              "- Effects marked as assumptions (such as how much dredging lowers floods) are what-ifs, not predictions.",
              "- Decisions must be made with communities, engineers and the relevant government agencies"
              + (f" ({place['agencies']})." if place and place.get("agencies") else ".")]
    return "\n".join(lines)


def write(area: str, summary: dict, place: dict | None = None) -> tuple[str, dict]:
    # Per-building detail is too long for a prompt and adds nothing to the plan.
    slim = json.loads(json.dumps(summary))
    for k in ("baseline", "with_measures"):
        if isinstance(slim.get(k), dict):
            slim[k].pop("buildings", None)
    slim["measure_assumptions"] = {k: v.get("assumption") for k, v in flood.MEASURES.items() if not k.startswith("_")}
    slim["model_defaults"] = flood.MEASURES["_defaults"]
    if place:
        slim["place"] = {k: place.get(k) for k in ("name", "country", "existing_work", "agencies", "option_examples",
                                                   "floor_height_m", "floor_height_note")}
    where = f", {place['country']}" if place and place.get("country") else ""
    prompt = PROMPT.format(area=area, where=where, flood_type=(place or {}).get("flood_type", "river flooding"),
                           facts=json.dumps(slim, indent=1, default=str))
    return llm.generate(prompt, lambda note: template_plan(area, slim, note, place))