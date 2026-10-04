"""Check every number in the pitch against the app's data files, and save the results as CSV tables.

It recounts straight from buildings.json / facilities.json / roads.json (nothing is copied from results.md)
and uses the backend's own flood rules (backend/app/flood.py, compare.py) for "water inside" and the measures.

Usage (from data-prep):
  python check_claims.py                    # all checks -> printed + CSV files in docs/checks/
  python check_claims.py --find nawaka      # every facility and area whose name contains "nawaka"
  python check_claims.py --level 2.5        # who/what is reached at a 2.5 m rise (also saved as CSV)

CSV files (open in Excel or Google Sheets):
  1_claims.csv        each pitch claim, the number from the data, and the file/field it comes from
  2_flood_curve.csv   buildings, people reached and people with water inside, every 0.25 m
  3_areas_at_2m.csv   people reached at 2 m, by area name
  4_facilities.csv    all facilities, in the order water reaches them
  5_measures.csv      people kept dry by each measure at 2 m and 3 m
  6_roads.csv         road km cut at 1-6 m
"""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "frontend" / "public" / "data"
OUT = ROOT / "docs" / "checks"
NEVER = 99
TOWN_CENTRE = (177.417, -17.80)   # lon, lat; circle of ~500 m (0.005 degrees)
FLOOR_M = 0.3

sys.path.insert(0, str(ROOT / "backend"))
try:
    from app import compare, flood  # Hedy's model: the same rules the app uses
except Exception as e:  # still useful without the backend
    flood = compare = None
    print(f"(backend not importable: {e}; 'water inside' and measures checks skipped)\n")


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save_csv(name, header, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    # utf-8-sig so Excel shows names like "Dr Naidu’s" correctly
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def print_table(title, header, rows):
    """Print rows as an aligned text table."""
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)))
    cells = [[str(c) for c in header]] + [[fmt(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(header))]
    # right-align a column only if every value in it is a number
    right = [all(is_num(r[i]) or r[i] in ("", "never") for r in cells[1:]) for i in range(len(header))]
    for k, r in enumerate(cells):
        print("  " + "  ".join(c.rjust(wd) if ra else c.ljust(wd) for c, wd, ra in zip(r, widths, right)))
        if k == 0:
            print("  " + "  ".join("-" * wd for wd in widths))


def fmt(v):
    if isinstance(v, float):
        return f"{v:,.7g}" if v != int(v) else f"{int(v):,}"
    if isinstance(v, int):
        return f"{v:,}"
    return "" if v is None else str(v)


def is_num(s):
    return s.replace(",", "").replace(".", "").replace("-", "").replace("%", "").isdigit()


def fac_level(x):
    return "never" if x["floods_at_m"] >= NEVER else x["floods_at_m"]


def report(title, filename, header, rows):
    print_table(title, header, rows)
    return save_csv(filename, header, rows)


# ---------------------------------------------------------------------------------------------
def find(q, b, f):
    q = q.lower()
    rows = [[x["id"], x.get("name") or "(no name)", x["type"], fac_level(x), round(x["ground_m"], 2),
             x.get("area") or "", x["lat"], x["lon"]]
            for x in sorted(f, key=lambda x: x["floods_at_m"])
            if q in (x.get("name") or "").lower() or q in (x.get("area") or "").lower()]
    print_table(f"Facilities matching '{q}'", ["id", "name", "type", "floods at (m)", "height above river (m)",
                                                "area", "lat", "lon"], rows)
    areas = {}
    for x in b:
        if q in (x.get("area") or "").lower():
            areas.setdefault(x["area"], []).append(x)
    rows = []
    for a, xs in areas.items():
        lv = sorted(x["floods_at_m"] for x in xs if x["floods_at_m"] < NEVER)
        rows.append([a, len(xs), round(sum(x["people"] for x in xs)), len(lv), lv[0] if lv else "-",
                     round(sum(x["people"] for x in xs if x["floods_at_m"] <= 2))])
    print_table(f"Areas matching '{q}'", ["area", "buildings", "people", "reached within 6 m",
                                           "first reached (m)", "people reached at 2 m"], rows)


def at_level(L, b, f, r):
    hit = [x for x in b if x["floods_at_m"] <= L]
    by_area = {}
    for x in hit:
        k = x.get("area") or "(no area name)"
        by_area[k] = by_area.get(k, 0) + x["people"]
    rows = [["Total", "buildings reached", len(hit)],
            ["Total", "people reached", round(sum(x["people"] for x in hit))],
            ["Total", "road km cut", round(sum(x["length_m"] for x in r if L - x["low_point_m"] >= FLOOR_M) / 1000, 1)]]
    rows += [["Area", a, round(p)] for a, p in sorted(by_area.items(), key=lambda kv: -kv[1])]
    rows += [["Facility", f"{x.get('name') or '(no name)'} ({x['type']})", f"reached at {x['floods_at_m']:g} m"]
             for x in sorted(f, key=lambda x: x["floods_at_m"]) if x["floods_at_m"] <= L]
    path = report(f"At a {L:g} m rise", f"at_level_{L:g}m.csv", ["kind", "what", "value"], rows)
    print(f"\nSaved {path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--find", help="search facility names and area names (case-insensitive)")
    ap.add_argument("--level", type=float, help="list what is reached at this river rise (m)")
    args = ap.parse_args()

    b, f, r = load("buildings.json"), load("facilities.json"), load("roads.json")
    s = load("hand_summary.json")
    if args.find:
        return find(args.find, b, f)
    if args.level is not None:
        return at_level(args.level, b, f, r)

    saved = []
    people_total = sum(x["people"] for x in b)
    ppl_at = lambda L: sum(x["people"] for x in b if x["floods_at_m"] <= L)  # noqa: E731

    # 2. flood curve (computed first; the claims table uses it)
    curve, prev = [], 0
    for i in range(0, 25):
        L = i * 0.25
        hit = [x for x in b if x["floods_at_m"] <= L]
        ppl = sum(x["people"] for x in hit)
        inside = flood.assess(L, b, f, r)["people_water_inside"] if flood else ""
        curve.append([L, len(hit), round(ppl), inside, round(ppl - prev)])
        prev = ppl
    jump = max(curve[1:], key=lambda c: c[4])

    # 3. areas at 2 m
    at2 = {}
    for x in b:
        if x["floods_at_m"] <= 2:
            k = x.get("area") or "(no area name)"
            at2[k] = at2.get(k, 0) + x["people"]
    areas = sorted(at2.items(), key=lambda kv: -kv[1])
    named = [(a, p) for a, p in areas if a != "(no area name)"]

    # town centre
    near = [x for x in b if math.hypot(x["lon"] - TOWN_CENTRE[0], x["lat"] - TOWN_CENTRE[1]) < 0.005]
    near_lv = [x["floods_at_m"] for x in near if x["floods_at_m"] < NEVER]

    fac = {x.get("name"): x for x in f if x.get("name")}
    fl = lambda n: fac_level(fac[n]) if n in fac else "not in data"  # noqa: E731
    km_cut = lambda L: round(sum(x["length_m"] for x in r if L - x["low_point_m"] >= FLOOR_M) / 1000, 1)  # noqa: E731
    named_bld = sum(1 for x in b if x.get("area"))

    # 1. claims table
    claims = [
        ["Coverage", "Buildings", "13,509", len(b), "buildings.json: number of entries"],
        ["Coverage", "Facilities", "46", len(f), "facilities.json: number of entries"],
        ["Coverage", "Road sections", "1,921", len(r), "roads.json: number of entries"],
        ["Coverage", "People in mapped buildings", "~35,000", round(people_total), "buildings.json: sum of people"],
        ["Coverage", "WorldPop people in whole map box", "66,880", s.get("worldpop_people_in_box"),
         "hand_summary.json: worldpop_people_in_box"],
        ["Coverage", "Share of residents in mapped buildings", "about half",
         f"{people_total / s['worldpop_people_in_box']:.0%}" if s.get("worldpop_people_in_box") else "",
         "the two lines above"],
        ["Coverage", "Buildings with an area name", "47%", f"{named_bld:,} ({named_bld / len(b):.0%})",
         "buildings.json: area"],
        ["Coverage", "Elevation data", "FABDEM", s.get("dem"), "hand_summary.json: dem"],
        ["Flood curve", "People reached at 0 m", "0", round(ppl_at(0)),
         "buildings.json: floods_at_m <= 0"],
        ["Flood curve", "People reached at 2 m", "~1,300", round(ppl_at(2)), "buildings.json: people where floods_at_m <= 2"],
        ["Flood curve", "People reached at 4 m", "~6,100", round(ppl_at(4)), "buildings.json: people where floods_at_m <= 4"],
        ["Flood curve", "People reached at 6 m", "~14,700", round(ppl_at(6)), "buildings.json: people where floods_at_m <= 6"],
        ["Flood curve", "Biggest jump in one 0.25 m step", "3 to 3.25 m, ~1,900",
         f"{jump[0] - 0.25:g} to {jump[0]:g} m: +{jump[4]:,} people", "2_flood_curve.csv: last column"],
        ["What floods first", "Most affected named community at 2 m", "Namotomoto ~390",
         f"{named[0][0]} {round(named[0][1])}" if named else "", "buildings.json: area, people, floods_at_m <= 2"],
        ["What floods first", "Second named community at 2 m", "Saunaka ~105",
         f"{named[1][0]} {round(named[1][1])}" if len(named) > 1 else "", "same"],
        ["What floods first", "People at 2 m with no area name", "(say 'named communities')",
         round(at2.get("(no area name)", 0)), "same"],
        ["What floods first", "Nawaka first reached at (m)", "0.75",
         min((x["floods_at_m"] for x in b if "nawaka" in (x.get("area") or "").lower()), default="not in data"),
         "buildings.json: area contains Nawaka, min floods_at_m"],
        ["What floods first", "Sabeto Primary School reached at (m)", "1.5", fl("Sabeto Primary School"),
         "facilities.json: floods_at_m"],
        ["What floods first", "Family Clinic reached at (m)", "3.75", fl("Family Clinic"), "facilities.json: floods_at_m"],
        ["What floods first", "Eye Clinic reached at (m)", "3.75", fl("EYE CLINIC"), "facilities.json: floods_at_m"],
        ["What floods first", "Nadi Fire Station reached at (m)", "5.5", fl("NADI FIRE STATION"), "facilities.json: floods_at_m"],
        ["What floods first", "First fire station of any name reached at (m)", "4 (unnamed)",
         min((x["floods_at_m"] for x in f if x["type"] == "fire_station"), default="none"),
         "facilities.json: type = fire_station"],
        ["Town centre", "Buildings within ~500 m of the centre", "483", len(near), "buildings.json: lon, lat"],
        ["Town centre", "Share reached within 6 m", "about 90%", f"{len(near_lv) / max(1, len(near)):.0%}",
         "buildings.json: floods_at_m < 99"],
        ["Town centre", "Median rise to reach them (m)", "5", statistics.median(near_lv) if near_lv else "",
         "buildings.json: median floods_at_m"],
        ["Roads", "Road km cut at 1 m", "17", km_cut(1), "roads.json: length_m where 1 - low_point_m >= 0.3"],
    ]

    # 5. measures
    measures = []
    if compare:
        opts = {"channel_clearing_m": 0.25, "nature_based": {"reduction_pct": 5},
                "raise_homes": {"count": 100, "height_m": 1.0}}
        names = {"channel_clearing_m": "Clear the river channel (-0.25 m)",
                 "nature_based": "Riverbank vegetation (-5% river rise)", "raise_homes": "Raise 100 homes by 1 m"}
        res = {L: compare.compare_options(L, opts, b, f, r, order=["nature_based", "channel_clearing_m", "raise_homes"])
               for L in (2.0, 3.0)}
        measures.append(["(people with water inside, no measure)",
                         res[2.0]["baseline"]["people_water_inside"], res[3.0]["baseline"]["people_water_inside"]])
        for k in opts:
            measures.append([names[k], *[next(o["at_design_level"]["people_protected"] for o in res[L]["options"]
                                              if o["key"] == k) for L in (2.0, 3.0)]])
        measures.append(["All three together", *[res[L]["layering"]["steps"][-1]["people_protected_so_far"]
                                                 for L in (2.0, 3.0)]])
        d = {m[0]: m for m in measures}
        claims += [
            ["Measures", "Raise 100 homes: people kept dry at 2 m", "~435", d[names["raise_homes"]][1], "backend compare.py"],
            ["Measures", "Clear channel: people kept dry at 2 m", "~130", d[names["channel_clearing_m"]][1], "backend compare.py"],
            ["Measures", "Vegetation: people kept dry at 2 m", "~80", d[names["nature_based"]][1], "backend compare.py"],
            ["Measures", "All three: people kept dry at 2 m", "~630", d["All three together"][1], "backend compare.py"],
        ]
        sw = {o["key"]: o["at_design_level"]["people_protected"]
              for o in compare.compare_options(3.25, opts, b, f, r)["options"]}
        claims += [
            ["Measures", "Clear channel: people kept dry at 3.25 m", "~1,640", sw["channel_clearing_m"], "backend compare.py"],
            ["Measures", "Raise 100 homes: people kept dry at 3.25 m", "~610", sw["raise_homes"], "backend compare.py"],
        ]

    saved.append(report("1. Pitch claims vs data", "1_claims.csv",
                        ["section", "claim", "pitch says", "data says", "where it comes from"], claims))
    saved.append(report("2. People as the river rises", "2_flood_curve.csv",
                        ["river rise (m)", "buildings reached", "people reached", "people water inside",
                         "new people reached in this step"], curve))
    print("  'water inside' = reached AND river rise > height above river + 0.3 m floor (backend/app/flood.py)")
    saved.append(report("3. People reached at 2 m, by area", "3_areas_at_2m.csv",
                        ["area", "people reached at 2 m"], [[a, round(p)] for a, p in areas]))
    saved.append(report("4. Facilities in the order water reaches them", "4_facilities.csv",
                        ["reached at (m)", "name", "type", "area", "height above river (m)", "lat", "lon"],
                        [[fac_level(x), x.get("name") or "(no name)", x["type"], x.get("area") or "",
                          round(x["ground_m"], 2), x["lat"], x["lon"]]
                         for x in sorted(f, key=lambda x: (x["floods_at_m"], x.get("name") or ""))]))
    if measures:
        saved.append(report("5. People kept dry by each measure", "5_measures.csv",
                            ["measure", "at 2 m", "at 3 m"], measures))
    saved.append(report("6. Roads cut", "6_roads.csv", ["river rise (m)", "road km cut"],
                        [[L, km_cut(L)] for L in range(1, 7)]))

    print("\nNot in these files (check the source instead): 26 floods since 1991 and the 2009 toll (cited reports), "
          "the 2016/2026 news reports (links in README), and the earlier two-elevation-dataset comparison.")
    print("\nSaved:")
    for p in saved:
        print("  ", p.relative_to(ROOT))


if __name__ == "__main__":
    main()
