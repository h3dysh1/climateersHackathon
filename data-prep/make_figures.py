"""Result figures and tables for the pitch, video and README → docs/figures/.

  1_measures.png      Which measure keeps the most people dry (at a 2 m and a 3 m river rise)
  2_what_floods_first.png   Named places and facilities, at the river rise that first reaches them
  3_flood_curve.png   People reached vs people with water inside their homes, 0-6 m
  results.md          The same numbers as tables

Reads the app's data files (frontend/public/data) and uses the backend's own flood model
(backend/app/flood.py, compare.py), so the figures match what the app shows.

Usage (from data-prep):  python make_figures.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "frontend" / "public" / "data"
OUT = ROOT / "docs" / "figures"
sys.path.insert(0, str(ROOT / "backend"))
from app import compare, flood  # noqa: E402

# Reference palette (validated: blue/orange pass CVD and contrast on the light surface)
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"

# Settings for the measures chart: the backend's "medium" presets (measures.json)
OPTIONS = {
    "channel_clearing_m": 0.25,                          # dredging lowers every flood by 0.25 m
    "nature_based": {"reduction_pct": 5},                # riverbank vegetation: 5% lower river rise
    "raise_homes": {"count": 100, "height_m": 1.0},      # raise 100 homes by 1 m
}
LABELS = {"channel_clearing_m": "Clear the river channel\n(−0.25 m)",
          "nature_based": "Riverbank vegetation\n(−5% river rise)",
          "raise_homes": "Raise 100 homes\nby 1 m",
          "all": "All three together"}
LEVELS = (2.0, 3.0)

# Facilities and places for the "what floods first" ladder (names exactly as in the data).
LADDER_FACILITIES = ["Sabeto Primary School", "Sabeto Muslim Primary School", "Family Clinic", "EYE CLINIC",
                     "Nadi Primary School", "NADI FIRE STATION", "Saunaka Village Community Hall",
                     "International School Nadi", "Nawaka Health Center", "Nawaka Primary School"]
NICE = {"EYE CLINIC": "Eye Clinic", "NADI FIRE STATION": "Nadi Fire Station", "Nawaka Health Center": "Nawaka Health Centre"}
TOWN_CENTRE = (177.417, -17.80)  # lon, lat; "within ~500 m"


def style(ax, title, subtitle):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=11)
    ax.figure.text(0.04, 0.95, title, fontsize=18, fontweight="bold", color=INK, va="top")
    ax.figure.text(0.04, 0.895, subtitle, fontsize=11.5, color=INK2, va="top")


def note(fig, text):
    fig.text(0.04, 0.025, text, fontsize=9.5, color=INK2)


def load():
    b = json.loads((DATA / "buildings.json").read_text())
    f = json.loads((DATA / "facilities.json").read_text())
    r = json.loads((DATA / "roads.json").read_text())
    return b, f, r


def fig_measures(b, f, r):
    rows = {k: [] for k in [*OPTIONS, "all"]}
    base_inside = []
    for L in LEVELS:
        res = compare.compare_options(L, OPTIONS, b, f, r, order=["nature_based", "channel_clearing_m", "raise_homes"])
        base_inside.append(res["baseline"]["people_water_inside"])
        for o in res["options"]:
            rows[o["key"]].append(o["at_design_level"]["people_protected"])
        rows["all"].append(res["layering"]["steps"][-1]["people_protected_so_far"])

    keys = list(rows)
    fig, ax = plt.subplots(figsize=(13.33, 7.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(left=0.24, right=0.95, top=0.80, bottom=0.12)
    h = 0.36
    for j, (L, col) in enumerate(zip(LEVELS, (BLUE, ORANGE))):
        ys = [i + (j - 0.5) * (h + 0.04) for i in range(len(keys))]
        vals = [rows[k][j] for k in keys]
        ax.barh(ys, vals, height=h, color=col, label=f"River {L:g} m above normal", zorder=3)
        for y, v in zip(ys, vals):
            ax.text(v + max(max(rows[k]) for k in keys) * 0.01, y, f"{v:,}", va="center", fontsize=11, color=INK)
    ax.set_yticks(range(len(keys)), [LABELS[k] for k in keys], fontsize=12, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("People kept dry inside their homes", fontsize=12, color=INK2)
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.legend(frameon=False, fontsize=11, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, labelcolor=INK)
    ax.set_xlim(0, max(max(v) for v in rows.values()) * 1.12)
    style(ax, "Which measure keeps the most people dry?",
          f"Without any measure, water gets inside the homes of {base_inside[0]:,} people at a 2 m rise "
          f"and {base_inside[1]:,} at 3 m (Nadi, model estimate)")
    note(fig, "Settings are the app's 'medium' what-ifs, not engineering designs. Homes to raise are chosen where 1 m keeps water out. "
              "Floors assumed 0.3 m above ground.")
    fig.savefig(OUT / "1_measures.png", facecolor=SURFACE)
    plt.close(fig)
    return rows, base_inside


def fig_ladder(b, f):
    import math
    fac = {x["name"]: x for x in f if x.get("name")}
    items = []
    for n in LADDER_FACILITIES:
        if n in fac and fac[n]["floods_at_m"] < 99:
            items.append((fac[n]["floods_at_m"], NICE.get(n, n), fac[n].get("type") or "facility"))
    # named communities: level at which the most people in that area are first reached is noisy, so report
    # the people reached at 2 m for the two most affected named villages
    at2 = {}
    for x in b:
        if x["floods_at_m"] <= 2 and x.get("area"):
            at2[x["area"]] = at2.get(x["area"], 0) + x["people"]
    top = sorted(at2.items(), key=lambda kv: -kv[1])[:2]
    if top:
        items.append((2.0, " & ".join(f"{a} (~{round(p, -1):,.0f} people)" for a, p in top), "most affected villages"))
    # town centre median
    near = sorted(x["floods_at_m"] for x in b if x["floods_at_m"] < 99 and
                  math.hypot(x["lon"] - TOWN_CENTRE[0], x["lat"] - TOWN_CENTRE[1]) < 0.005)
    if near:
        items.append((near[len(near) // 2], "Nadi town centre (half its buildings reached)", "town"))
    first = sum(1 for x in b if x["floods_at_m"] <= 1.0)
    items.append((1.0, f"First {first:,} buildings, along rivers and streams", "homes"))

    # group items at the same level into one label
    groups = {}
    for lv, name, kind in items:
        groups.setdefault(round(lv, 2), []).append(name)
    levels = sorted(groups)

    fig, ax = plt.subplots(figsize=(13.33, 7.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.82, bottom=0.10)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.3)
    ax.axvline(1.0, color=GRID, linewidth=2, zorder=1)
    # spread labels vertically so they never overlap (min gap), keeping a leader to the true level
    min_gap = 0.42
    ylab, last = [], -1e9
    for lv in levels:
        y = max(lv, last + min_gap)
        ylab.append(y)
        last = y
    shift = max(0, ylab[-1] - 6.15)
    ylab = [y - shift for y in ylab]
    for lv, y in zip(levels, ylab):
        ax.scatter([1.0], [lv], s=90, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.plot([1.0, 1.6, 1.8], [lv, y, y], color=INK2, linewidth=0.8, zorder=2)
        ax.text(1.95, y, f"{lv:g} m", fontsize=12, fontweight="bold", color=INK, va="center")
        ax.text(2.75, y, "  ·  ".join(groups[lv]), fontsize=12, color=INK, va="center")
    ax.set_xticks([])
    ax.set_yticks(range(0, 7), [f"{i} m" for i in range(0, 7)])
    ax.spines["bottom"].set_visible(False)
    ax.set_ylabel("River rise above normal", fontsize=12, color=INK2)
    style(ax, "What floods first as the Nadi River rises",
          "Each place at the river rise when floodwater first reaches it (model estimate, Nadi, 0–6 m)")
    note(fig, "Riverside villages Namotomoto and Nawaka are also named in flood reports from April 2016 and March 2026. "
              "Facilities from OpenStreetMap.")
    fig.savefig(OUT / "2_what_floods_first.png", facecolor=SURFACE)
    plt.close(fig)
    return [(lv, groups[lv]) for lv in levels]


def fig_curve(b, f, r):
    levels = [round(0.25 * i, 2) for i in range(0, 25)]
    reached, inside = [], []
    for L in levels:
        a = flood.assess(L, b, f, r)
        reached.append(a["people_reached"])
        inside.append(a["people_water_inside"])
    fig, ax = plt.subplots(figsize=(13.33, 7.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    fig.subplots_adjust(left=0.09, right=0.85, top=0.80, bottom=0.12)
    ax.plot(levels, reached, color=BLUE, linewidth=2.5, label="People whose home floodwater reaches", zorder=3)
    ax.plot(levels, inside, color=ORANGE, linewidth=2.5, label="People with water inside their home", zorder=3)
    gap = max(reached) * 0.09  # keep the two end labels apart
    y_top, y_bot = reached[-1], inside[-1]
    if y_top - y_bot < gap:
        mid = (y_top + y_bot) / 2
        y_top, y_bot = mid + gap / 2, mid - gap / 2
    for ys, yl, col, lab in ((reached, y_top, BLUE, "Reached"), (inside, y_bot, ORANGE, "Water inside")):
        ax.text(levels[-1] + 0.1, yl, f"{lab}\n{ys[-1]:,}", color=INK, fontsize=11, va="center")
        ax.scatter([levels[-1]], [ys[-1]], s=64, color=col, edgecolor=SURFACE, linewidth=2, zorder=4, clip_on=False)
    for L in (2.0, 4.0):
        i = levels.index(L)
        ax.scatter([L], [reached[i]], s=64, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=4)
        ax.annotate(f"{L:g} m: {reached[i]:,} people reached", (L, reached[i]), xytext=(-10, 18),
                    textcoords="offset points", ha="right", fontsize=11, color=INK)
    ax.set_xlim(0, 6)
    ax.set_ylim(0, max(reached) * 1.08)
    ax.set_xlabel("River rise above normal (m)", fontsize=12, color=INK2)
    ax.set_ylabel("People", fontsize=12, color=INK2)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(color=GRID, linewidth=0.8, zorder=0)
    ax.legend(frameon=False, fontsize=11, loc="upper left", labelcolor=INK)
    style(ax, "How many people flood as the river rises",
          "Nadi, 13,509 buildings, WorldPop 2020 population (about 35,000 people in mapped buildings)")
    note(fig, "Planning model (height above nearest drainage on FABDEM), not a flow simulation. "
              "'Water inside' assumes floors 0.3 m above ground.")
    fig.savefig(OUT / "3_flood_curve.png", facecolor=SURFACE)
    plt.close(fig)
    return levels, reached, inside


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    b, f, r = load()
    m_rows, base_inside = fig_measures(b, f, r)
    ladder = fig_ladder(b, f)
    levels, reached, inside = fig_curve(b, f, r)

    md = ["# Nadi flood results (generated by `data-prep/make_figures.py`)", "",
          "All heights are metres the river rises above normal. Model estimates, not predictions.", "",
          "## 1. People kept dry by each measure", "",
          "| Measure | at 2 m | at 3 m |", "| --- | ---: | ---: |",
          f"| *(people with water inside, no measures)* | {base_inside[0]:,} | {base_inside[1]:,} |"]
    md += [f"| {LABELS[k].replace(chr(10), ' ')} | {v[0]:,} | {v[1]:,} |" for k, v in m_rows.items()]
    md += ["", "## 2. What floods first", "", "| River rise | Place |", "| ---: | --- |"]
    md += [f"| {lv:g} m | {'; '.join(names)} |" for lv, names in ladder]
    md += ["", "## 3. People reached and with water inside", "",
           "| River rise | People reached | People with water inside |", "| ---: | ---: | ---: |"]
    md += [f"| {L:g} m | {a:,} | {c:,} |" for L, a, c in zip(levels, reached, inside) if (L * 2) == int(L * 2)]
    (OUT / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for p in sorted(OUT.iterdir()):
        print("wrote", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
