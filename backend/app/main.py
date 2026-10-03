"""FastAPI backend for Restore to Protect. Endpoints are documented in docs/contracts.md
and interactively at /docs when the server is running."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import claude_client, restoration

load_dotenv()

app = FastAPI(title="Restore to Protect API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_SEGMENTS = 2000


class Segment(BaseModel):
    id: str
    # Older single-type fields (treated as mangroves)...
    existing_width_m: float = Field(ge=0, default=0)
    restorable_width_m: float = Field(ge=0, default=0)
    restorable_ha: float = Field(ge=0, default=0)
    # ...or per-type widths, e.g. {"mangrove": 80, "saltmarsh": 40}
    existing_by_type: dict[str, float] | None = None
    restorable_by_type: dict[str, float] | None = None
    restorable_ha_by_type: dict[str, float] | None = None
    surge_people: float = Field(ge=0, default=0)


def _check_types(types: list[str] | None) -> list[str] | None:
    if types is None:
        return None
    unknown = [t for t in types if t not in restoration.ECOSYSTEMS]
    if unknown:
        raise ValueError(f"Unknown ecosystem types: {unknown}. Known: {list(restoration.ECOSYSTEMS)}")
    return types


class _Types(BaseModel):
    types: list[str] | None = Field(default=None, description="ecosystem types to restore; omit for all verified types")

    @field_validator("types")
    @classmethod
    def _known(cls, v):
        return _check_types(v)


class ScenarioIn(_Types):
    restore_ids: list[str]
    segments: list[Segment] = Field(max_length=MAX_SEGMENTS)
    years: float | None = Field(default=None, ge=0, le=200, description="years since planting; omit for fully grown")


class RankIn(_Types):
    segments: list[Segment] = Field(max_length=MAX_SEGMENTS)


class BudgetIn(RankIn):
    hectares: float = Field(gt=0, le=100_000)


class PlanIn(BaseModel):
    area_name: str = Field(min_length=1, max_length=80)
    summary: dict


def _dump(segments: list[Segment]) -> list[dict]:
    return [s.model_dump() for s in segments]


@app.get("/health")
def health():
    return {"ok": True, "mock": claude_client.is_mock(), "verified_types": restoration.wave_types()}


@app.get("/ecosystems")
def ecosystems():
    """Every ecosystem type, its parameters, evidence and whether it counts yet."""
    return restoration.ECOSYSTEMS


@app.post("/scenario")
def scenario(body: ScenarioIn):
    """Restore the given segments and compare protection before/after (optionally at a given year)."""
    return restoration.run_scenario(_dump(body.segments), body.restore_ids, body.years, body.types)


@app.post("/rank-sites")
def rank_sites(body: RankIn):
    """Restorable sites ranked by people protected per hectare."""
    return {"sites": restoration.rank_sites(_dump(body.segments), body.types)}


@app.post("/select-sites")
def select_sites(body: BudgetIn):
    """"Restore N hectares": pick the best sites within the budget and return the scenario."""
    return restoration.select_by_budget(_dump(body.segments), body.hectares, body.types)


@app.post("/restoration-plan")
def restoration_plan(body: PlanIn):
    """AI-written plain-language plan. Ecosystem evidence is attached automatically."""
    used = body.summary.get("types") or restoration.wave_types()
    summary = {**body.summary, "ecosystems": {
        t: {k: restoration.ECOSYSTEMS[t][k] for k in ("label", "maturity_years", "evidence")}
        for t in used if t in restoration.ECOSYSTEMS}}
    try:
        markdown, cached = claude_client.write_plan(body.area_name, summary)
    except claude_client.PlanError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"markdown": markdown, "cached": cached, "mock": claude_client.is_mock()}