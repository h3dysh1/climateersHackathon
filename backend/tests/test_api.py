import os

# Tests always run in mock mode (an empty value also stops load_dotenv reading a real key).
os.environ["ANTHROPIC_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.restoration import protection_band, wave_reduction  # noqa: E402

client = TestClient(app)

SEGMENTS = [
    {"id": "s1", "existing_width_m": 0, "restorable_width_m": 400, "restorable_ha": 20, "surge_people": 120},
    {"id": "s2", "existing_width_m": 250, "restorable_width_m": 0, "restorable_ha": 0, "surge_people": 40},
    {"id": "s3", "existing_width_m": 0, "restorable_width_m": 100, "restorable_ha": 5, "surge_people": 30},
]


def test_health():
    assert client.get("/health").json() == {"ok": True, "mock": True}


def test_wave_model_is_conservative_and_capped():
    assert wave_reduction(0) == 0
    assert wave_reduction(100) == 0.13
    assert wave_reduction(2000) == 0.66
    assert protection_band(0) == "exposed"
    assert protection_band(400) == "strong"


def test_scenario_moves_people_to_better_protection():
    r = client.post("/scenario", json={"restore_ids": ["s1"], "segments": SEGMENTS}).json()
    assert r["restored"] == ["s1"]
    assert r["hectares"] == 20
    assert r["people_better_protected"] == 120
    assert r["before"]["exposed"] == 150 and r["after"]["exposed"] == 30
    assert sum(r["before"].values()) == sum(r["after"].values())


def test_restoration_plan_mock():
    r = client.post("/restoration-plan", json={"area_name": "Test", "summary": {"hectares": 20}})
    assert "MOCK" in r.json()["markdown"]
