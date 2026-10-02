import os

# Tests always run in mock mode (an empty value also stops load_dotenv reading a real key).
os.environ["ANTHROPIC_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

BUILDINGS = [
    {"id": "a", "exposure": 0.9, "vulnerability": 0.8, "risk": 0.72, "band": "high"},
    {"id": "b", "exposure": 0.8, "vulnerability": 0.7, "risk": 0.56, "band": "high"},
    {"id": "c", "exposure": 0.5, "vulnerability": 0.6, "risk": 0.30, "band": "medium"},
    {"id": "d", "exposure": 0.2, "vulnerability": 0.5, "risk": 0.10, "band": "low"},
]


def test_health():
    assert client.get("/health").json() == {"ok": True, "mock": True}


def test_plan_upgrades_moves_buildings_out_of_high():
    r = client.post("/plan-upgrades", json={"budget": 2, "buildings": BUILDINGS}).json()
    assert r["upgraded"] == ["a", "b"]
    assert r["before"] == {"high": 2, "medium": 1, "low": 1}
    assert r["after"]["high"] == 0
    assert sum(r["after"].values()) == 4


def test_classify_mock():
    r = client.post("/classify", json={"id": "b0001", "image_base64": "aGVsbG8="}).json()
    assert r["id"] == "b0001" and r["mock"] is True
    assert r["roof_material"] in ("corrugated_iron", "concrete", "timber")


def test_resilience_plan_mock():
    r = client.post("/resilience-plan", json={"area_name": "Test", "summary": {"before": {"high": 5}, "after": {"high": 1}}})
    assert "MOCK" in r.json()["markdown"]
