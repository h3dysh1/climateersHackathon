import os

# Tests never call the real Gemini: blank key (also stops load_dotenv reading a real .env key).
for k in ("GEMINI_API_KEY", "LLM_MODEL"):
    os.environ[k] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import llm  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

# Small made-up town: ground heights in m above sea level.
BUILDINGS = [
    {"id": "low1", "ground_m": 1.0, "people": 5},                      # floods first
    {"id": "low2", "ground_m": 1.2, "floods_at_m": 1.5, "people": 4},  # sits behind a bank: reached at 1.5 m
    {"id": "mid", "ground_m": 2.0, "people": 6, "floor_height_m": 1.0},  # raised house
    {"id": "high", "ground_m": 5.0, "people": 3},                      # stays dry
]
FACILITIES = [
    {"id": "clinic", "name": "Town clinic", "type": "clinic", "ground_m": 1.1},
    {"id": "school", "name": "Hill school", "type": "school", "ground_m": 6.0},
]
ROADS = [{"id": "r1", "low_point_m": 1.0, "length_m": 800}, {"id": "r2", "low_point_m": 4.0, "length_m": 500}]
AREA = {"buildings": BUILDINGS, "facilities": FACILITIES, "roads": ROADS}


def flood(level, measures=None):
    body = {**AREA, "level_m": level}
    if measures:
        body["measures"] = measures
    r = client.post("/flood", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_measures():
    h = client.get("/health").json()
    assert h["ok"] and h["llm_provider"] == "template"
    m = client.get("/measures").json()
    assert [k for k in m if not k.startswith("_")] == ["channel_clearing_m", "raise_homes", "nature_based"]
    assert {m[k]["category"] for k in m if not k.startswith("_")} == {"channel", "home", "nature-based"}
    assert all("presets" in m[k] and m[k]["sources"] for k in m if not k.startswith("_"))


def test_baseline_counts_at_a_level():
    b = flood(2.0)["baseline"]
    # 2.0 m: low1 (floor 1.3) and low2 (floor 1.5, reached at 1.5) have water inside;
    # mid is reached (ground 2.0) but its floor is 3.0, so no water inside; high is dry.
    assert b["buildings_reached"] == 3
    assert b["buildings_water_inside"] == 2 and b["people_water_inside"] == 9
    assert [f["id"] for f in b["facilities_flooded"]] == ["clinic"]
    assert b["roads_cut"] == ["r1"] and b["roads_cut_km"] == 0.8
    # depths: low1 1.0 m (band 1-2 m), low2 0.8 m (0.5-1 m), mid 0.0 m (under 0.5 m)
    assert b["depth_bands"] == {"under_0_5m": 1, "0_5_to_1m": 1, "1_to_2m": 1, "over_2m": 0}


def test_connectivity_respected():
    # At 1.4 m low2 is above its ground but water can't reach it yet (floods_at_m 1.5).
    ids = {x["id"]: x for x in flood(1.4)["baseline"]["buildings"]}
    assert ids["low2"]["depth_m"] == 0 and not ids["low2"]["water_inside"]
    assert ids["low1"]["water_inside"]


def test_raising_homes_keeps_water_out():
    r = flood(2.0, {"raise_homes": {"count": 2, "height_m": 1.0}})
    assert r["with_measures"]["homes_raised"] == ["low1", "low2"]  # the two that flood first
    assert r["with_measures"]["people_water_inside"] == 0
    assert r["saved"]["people_kept_dry_inside"] == 9 and r["saved"]["homes_kept_dry_inside"] == 2


def test_homes_too_deep_are_not_wasted_on_raising():
    # At 3.0 m: low1 floor 1.3 (1.7 m of water inside) and low2 floor 1.5 (1.5 m) are too deep
    # for a 1 m raise; mid floor 3.0 is dry. So raising should pick nobody and flag 2 deep homes.
    r = flood(3.0, {"raise_homes": {"count": 5, "height_m": 1.0}})
    assert r["with_measures"]["homes_raised"] == []
    assert r["baseline"]["homes_too_deep_to_raise"] == 2
    # A 2 m raise does help both.
    r = flood(3.0, {"raise_homes": {"count": 5, "height_m": 2.0}})
    assert r["with_measures"]["homes_raised"] == ["low1", "low2"] and r["saved"]["people_kept_dry_inside"] == 9


def test_design_level_fixes_which_homes_are_raised():
    # Chosen at 2.0 m, then assessed at 1.4 m: same homes stay raised.
    r = flood(1.4, {"raise_homes": {"count": 2, "design_level_m": 2.0}})
    assert r["with_measures"]["homes_raised"] == ["low1", "low2"]


def test_channel_clearing_lowers_floods():
    r = flood(2.0, {"channel_clearing_m": 0.6})
    a = r["with_measures"]
    assert a["effective_level_m"] == 1.4
    assert a["people_water_inside"] == 5  # only low1 (floor 1.3) still has water inside
    assert a["facilities_flooded"] == [] and r["saved"]["facilities_protected"] == 1
    assert a["roads_cut"] == ["r1"]  # 1.4 - 1.0 = 0.4 m deep, still impassable


def test_curve_rises_with_level_and_measures_help():
    r = client.post("/flood-curve", json={**AREA, "min_m": 0, "max_m": 6, "step_m": 1,
                                         "measures": {"raise_homes": {"count": 2}}}).json()["levels"]
    people = [x["people_water_inside"] for x in r]
    assert people == sorted(people) and people[0] == 0 and people[-1] == 18
    assert all(x["people_water_inside_with_measures"] <= x["people_water_inside"] for x in r)


def test_bad_inputs_rejected():
    assert client.post("/flood", json={**AREA, "level_m": 99}).status_code == 422
    assert client.post("/flood-curve", json={**AREA, "min_m": 5, "max_m": 1}).status_code == 422
    assert client.post("/flood", json={"buildings": [{"id": "x"}], "level_m": 1}).status_code == 422


def test_plan_without_key_uses_builtin_writer():
    summary = flood(2.0, {"raise_homes": {"count": 2}})
    r = client.post("/flood-plan", json={"area_name": "Nadi", "place": "nadi", "summary": summary}).json()
    assert r["provider"] == "template" and r["fallback"] is False
    md = r["markdown"]
    assert md.startswith("# Flood resilience plan: Nadi") and "**9 people**" in md and "Town clinic" in md
    assert "Nadi Flood Alleviation Project" in md and "HAND" in md


def test_gemini_is_picked_and_prompt_is_slim(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    seen = []

    def ok(prompt):
        seen.append(prompt)
        return "# AI plan"
    monkeypatch.setitem(llm.PROVIDERS, "gemini", ok)
    summary = flood(2.0)
    first = client.post("/flood-plan", json={"area_name": "Nadi", "summary": summary}).json()
    second = client.post("/flood-plan", json={"area_name": "Nadi", "summary": summary}).json()
    assert first["provider"] == "gemini" and first["model"] == "gemini-2.5-flash"
    assert first["markdown"] == "# AI plan" and second["cached"] is True and len(seen) == 1
    assert '"buildings":' not in seen[0]  # per-building detail stripped from the prompt
    assert "measure_assumptions" in seen[0]


def test_free_tier_limit_falls_back(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    def limited(prompt):
        raise RuntimeError("Client error '429 Too Many Requests'")
    monkeypatch.setitem(llm.PROVIDERS, "gemini", limited)
    r = client.post("/flood-plan", json={"area_name": "Nadi", "summary": flood(1.5)}).json()
    assert r["fallback"] is True and r["error"] == "free-tier limit reached"
    assert "unavailable" in r["markdown"] and r["markdown"].startswith("# Flood resilience plan")


def test_gemini_request_shape(monkeypatch):
    import httpx
    monkeypatch.setenv("GEMINI_API_KEY", "k123")
    sent = {}

    class R:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "hidden", "thought": True}, {"text": "# Plan"}]}}]}

    def fake_post(url, **kw):
        sent.update(url=url, **kw)
        return R()
    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm._gemini("hello") == "# Plan"  # thinking parts are dropped
    assert sent["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert sent["headers"]["x-goog-api-key"] == "k123"
    assert sent["json"]["generationConfig"]["maxOutputTokens"] == 8192


# --- most affected areas ---------------------------------------------------------

def _town():
    # Two neighbourhoods ~1 km apart: "Riverside" is low and crowded, "Hilltop" mostly dry.
    b = []
    for i in range(10):
        b.append({"id": f"r{i}", "ground_m": 0.5 + i * 0.05, "people": 5, "lon": 177.4400 + i * 0.00003, "lat": -17.800})
    for i in range(10):
        b.append({"id": f"h{i}", "ground_m": 1.5 + i * 0.5, "people": 4, "lon": 177.4500 + i * 0.00003, "lat": -17.790})
    return b


def test_hotspots_rank_worst_area_first_on_a_grid():
    fac = [{"id": "c1", "name": "Riverside clinic", "ground_m": 0.6, "lon": 177.4405, "lat": -17.800}]
    r = client.post("/hotspots", json={"level_m": 2.0, "buildings": _town(), "facilities": fac}).json()
    assert r["grouping"] == "grid 250 m" and r["areas_affected"] == 2
    first, second = r["areas"]
    assert first["rank"] == 1 and first["people_water_inside"] == 50  # all 10 riverside homes
    assert first["people_deep_water"] == 50 and first["facilities_flooded"] == ["Riverside clinic"]
    assert second["people_water_inside"] == 4  # only the lowest hilltop home (ground 1.5, floor 1.8)
    assert abs(first["lon"] - 177.441) < 0.003 and abs(first["lat"] + 17.800) < 0.003
    assert r["people_water_inside_total"] == 54 and r["top_areas_share_of_people"] == 1.0


def test_hotspots_group_by_name_when_given():
    b = _town()
    for x in b:
        x["area"] = "Riverside" if x["id"].startswith("r") else "Hilltop"
    r = client.post("/hotspots", json={"level_m": 2.0, "buildings": b, "top": 1}).json()
    assert r["grouping"] == "name" and [a["name"] for a in r["areas"]] == ["Riverside"]
    assert r["top_areas_share_of_people"] == round(50 / 54, 2)


def test_hotspots_need_locations():
    r = client.post("/hotspots", json={"level_m": 2.0, "buildings": BUILDINGS}).json()
    assert r["areas"] == [] and "lon/lat" in r["note"]


# --- the three options and side-by-side comparison --------------------------------

def _named_town():
    b = _town()
    for x in b:
        x["area"] = "Riverside" if x["id"].startswith("r") else "Hilltop"
    return b


def test_vegetation_effect_fades_for_big_floods():
    from app import flood as f
    assert abs(f.nature_reduction_m(2.0, 10) - 0.2) < 1e-9   # full 10% up to 2 m
    assert abs(f.nature_reduction_m(4.0, 10) - 0.4 * 0.75) < 1e-9  # halfway to the fade
    assert abs(f.nature_reduction_m(8.0, 10) - 0.8 * 0.5) < 1e-9   # half effect beyond 6 m
    assert f.nature_reduction_m(0, 10) == 0
    r = flood(2.0, {"nature_based": {"reduction_pct": 10}})
    assert r["with_measures"]["effective_level_m"] == 1.8


def test_raise_homes_respects_target_area():
    b = _named_town()
    r = client.post("/flood", json={"buildings": b, "level_m": 2.0,
                                    "measures": {"raise_homes": {"count": 20, "height_m": 2.0, "target": {"area": "Hilltop"}}}}).json()
    assert all(i.startswith("h") for i in r["with_measures"]["homes_raised"])


def test_target_by_circle_around_a_hotspot():
    b = _town()
    t = {"lon": 177.4401, "lat": -17.800, "radius_m": 200}
    r = client.post("/flood", json={"buildings": b, "level_m": 2.0,
                                    "measures": {"raise_homes": {"count": 50, "height_m": 2.0, "target": t}}}).json()
    assert len(r["with_measures"]["homes_raised"]) == 10
    assert all(i.startswith("r") for i in r["with_measures"]["homes_raised"])


OPTIONS = {"channel_clearing_m": 0.5, "nature_based": {"reduction_pct": 10},
           "raise_homes": {"count": 5, "height_m": 1.0, "target": {"area": "Riverside"}}}


def _compare(**extra):
    body = {"level_m": 2.0, "buildings": _named_town(), "options": OPTIONS, "target": {"area": "Riverside"},
            "min_m": 0, "max_m": 4, "step_m": 0.5, **extra}
    r = client.post("/compare-measures", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_three_options_side_by_side():
    r = _compare()
    assert r["layering"] is None and r["baseline"]["people_water_inside"] == 54
    by = {o["key"]: o for o in r["options"]}
    assert set(by) == {"channel_clearing_m", "nature_based", "raise_homes"}
    assert [o["rank"] for o in r["options"]] == [1, 2, 3]
    ppl = [o["at_design_level"]["people_protected"] for o in r["options"]]
    assert ppl == sorted(ppl, reverse=True)
    assert by["channel_clearing_m"]["at_design_level"]["flood_lowered_by_m"] == 0.5
    assert by["nature_based"]["at_design_level"]["flood_lowered_by_m"] == 0.2
    assert by["nature_based"]["co_benefits"] and by["nature_based"]["sources"]
    assert by["raise_homes"]["effort"]["homes_raised"] == 5
    assert by["raise_homes"]["people_protected_per_home_raised"] == 5
    assert by["raise_homes"]["target_area"]["people_water_inside_before"] == 50
    assert len(r["baseline"]["curve"]) == 9 and len(by["nature_based"]["curve"]) == 9
    for o in r["options"]:  # no option makes any flood worse
        for p, q in zip(o["curve"], r["baseline"]["curve"]):
            assert p["people_water_inside"] <= q["people_water_inside"]


def test_layering_in_order_adds_up_and_order_matters():
    # A 0.5 m lift can't save Riverside homes at a 2 m flood, but can once the river is lowered 0.5 m.
    opts = {"channel_clearing_m": 0.5, "raise_homes": {"count": 5, "height_m": 0.5, "target": {"area": "Riverside"}}}
    raise_first = _compare(options=opts, order=["raise_homes", "channel_clearing_m"])["layering"]
    raise_last = _compare(options=opts, order=["channel_clearing_m", "raise_homes"])["layering"]
    assert raise_first["steps"][0]["homes_raised"] == 0 and raise_last["steps"][1]["homes_raised"] == 5
    for lay in (raise_first, raise_last):
        steps = lay["steps"]
        assert [s["step"] for s in steps] == [1, 2]
        assert sum(s["people_added_protection"] for s in steps) == steps[-1]["people_protected_so_far"]
        assert steps[-1]["people_still_water_inside"] + steps[-1]["people_protected_so_far"] == 54
        assert len(lay["orders_compared"]) == 2
    # Raising last targets homes still flooding after the river is lowered, so it protects more.
    assert raise_last["steps"][-1]["people_protected_so_far"] > raise_first["steps"][-1]["people_protected_so_far"]
    assert raise_last["orders_compared"][0]["order"] == ["channel_clearing_m", "raise_homes"]


def test_layering_all_three_lists_every_order():
    lay = _compare(order=["nature_based", "channel_clearing_m", "raise_homes"])["layering"]
    assert len(lay["orders_compared"]) == 6 and len(lay["steps"]) == 3
    assert lay["steps"][1]["flood_lowered_by_m"] == 0.7  # 0.2 from vegetation + 0.5 channel clearing


def test_compare_rejects_bad_requests():
    b = _named_town()
    base = {"level_m": 2, "buildings": b}
    assert client.post("/compare-measures", json={**base, "options": {}}).status_code == 422
    assert client.post("/compare-measures", json={**base, "options": {"channel_clearing_m": 0.5},
                                                  "order": ["raise_homes"]}).status_code == 422
    assert client.post("/compare-measures", json={**base, "options": OPTIONS,
                                                  "order": ["raise_homes", "raise_homes"]}).status_code == 422
    assert client.post("/compare-measures", json={**base, "options": {"floodwall": {"crest_m": 2}}}).status_code == 422


def test_places_are_listed_and_feed_the_plan():
    p = client.get("/places").json()
    assert p["nadi"]["country"] == "Fiji" and len(p["nadi"]["bbox"]) == 4
    r = client.post("/flood-plan", json={"area_name": "Nadi", "place": "nadi", "summary": flood(2.0, {"channel_clearing_m": 0.25})})
    assert r.status_code == 200 and "Nadi Flood Alleviation Project" in r.json()["markdown"]
    assert "silt" in r.json()["markdown"]
    plain = client.post("/flood-plan", json={"area_name": "Elsewhere", "summary": flood(2.0)}).json()["markdown"]
    assert "Nadi" not in plain and "Fiji" not in plain
    assert client.post("/flood-plan", json={"area_name": "X", "place": "atlantis", "summary": {}}).status_code == 404
    