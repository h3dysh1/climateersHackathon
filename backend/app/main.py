"""FastAPI backend for the river-flood planning tool (any town; settings in places/<town>.json).
Try every endpoint at http://localhost:8000/docs while the server is running."""
import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from . import compare, flood, hotspots, llm, places, plan

load_dotenv()

app = FastAPI(title="Flood Planning API", version="0.4.0", root_path="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_ITEMS = 20_000


# --- request shapes -------------------------------------------------------------

class Building(BaseModel):
    id: str
    ground_m: float = Field(description="height above the nearest river or sea (HAND), m")
    floods_at_m: float | None = Field(default=None, description="river rise (m) at which connected floodwater first reaches it")
    floor_height_m: float | None = Field(default=None, ge=0, le=10)
    people: float = Field(default=0, ge=0)
    type: str = "home"
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    area: str | None = Field(default=None, description="optional settlement/suburb name to group by")


class Facility(BaseModel):
    id: str
    name: str | None = None
    type: str | None = None  # clinic, school, substation, shelter...
    ground_m: float
    floods_at_m: float | None = None
    floor_height_m: float | None = Field(default=None, ge=0, le=10)
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    area: str | None = None


class Road(BaseModel):
    id: str
    low_point_m: float = Field(description="lowest HAND along the road section (bridges excluded), m")
    length_m: float = Field(default=0, ge=0)


class Target(BaseModel):
    """Where a measure applies: a named area, or a circle around a point (e.g. a hotspot). Omit for town-wide."""
    area: str | None = None
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    radius_m: float = Field(default=250, gt=0, le=20_000)


class RaiseHomes(BaseModel):
    count: int = Field(ge=0, le=MAX_ITEMS)
    height_m: float = Field(default=flood.MEASURES["raise_homes"]["default_height_m"], gt=0, le=5)
    design_level_m: float | None = Field(default=None, ge=-5, le=30,
                                         description="flood level used to choose homes; defaults to the level assessed")
    target: Target | None = None


class NatureBased(BaseModel):
    reduction_pct: float = Field(default=flood.MEASURES["nature_based"]["default_reduction_pct"], ge=0, le=30,
                                 description="your assumption: % lower river rise for floods up to 2 m (fades to half by 6 m)")


class Measures(BaseModel):
    """The three options. Any can be left out."""
    channel_clearing_m: float | None = Field(default=None, ge=0, le=2, description="dredging/desilting: lower every flood by this much, m")
    nature_based: NatureBased | None = None
    raise_homes: RaiseHomes | None = None


class Area(BaseModel):
    buildings: list[Building] = Field(max_length=MAX_ITEMS)
    facilities: list[Facility] = Field(default_factory=list, max_length=MAX_ITEMS)
    roads: list[Road] = Field(default_factory=list, max_length=MAX_ITEMS)
    measures: Measures | None = None


class FloodIn(Area):
    level_m: float = Field(ge=-5, le=30, description="how far the river rises above its normal level, m")


class CurveIn(Area):
    min_m: float = Field(default=0, ge=-5, le=30)
    max_m: float = Field(default=6, ge=-5, le=30)
    step_m: float = Field(default=0.25, gt=0, le=5)

    @model_validator(mode="after")
    def _range(self):
        if self.max_m < self.min_m:
            raise ValueError("max_m must be >= min_m")
        if (self.max_m - self.min_m) / self.step_m > 400:
            raise ValueError("too many levels; use a bigger step_m")
        return self


class HotspotsIn(BaseModel):
    level_m: float = Field(ge=-5, le=30, description="how far the river rises above its normal level, m")
    buildings: list[Building] = Field(max_length=MAX_ITEMS)
    facilities: list[Facility] = Field(default_factory=list, max_length=MAX_ITEMS)
    cell_m: float = Field(default=250, ge=50, le=5000, description="grid cell size when buildings have no area names")
    top: int = Field(default=10, ge=1, le=100)


class CompareIn(BaseModel):
    level_m: float = Field(ge=-5, le=30, description="design flood: how far the river rises above normal, m")
    buildings: list[Building] = Field(max_length=MAX_ITEMS)
    facilities: list[Facility] = Field(default_factory=list, max_length=MAX_ITEMS)
    roads: list[Road] = Field(default_factory=list, max_length=MAX_ITEMS)
    options: Measures = Field(description="settings for each option to compare (leave out ones you don't want)")
    order: list[Literal["channel_clearing_m", "nature_based", "raise_homes"]] | None = Field(
        default=None, description="optional: layer these options in this order, e.g. ['nature_based', 'raise_homes']")
    target: Target | None = Field(default=None, description="area to report on separately, e.g. the #1 hotspot")
    min_m: float = Field(default=0, ge=-5, le=30)
    max_m: float = Field(default=6, ge=-5, le=30)
    step_m: float = Field(default=0.5, gt=0, le=5)

    @model_validator(mode="after")
    def _range(self):
        if self.max_m < self.min_m:
            raise ValueError("max_m must be >= min_m")
        chosen = self.options.model_dump(exclude_none=True)
        if not chosen:
            raise ValueError("choose at least one option")
        if self.order:
            if len(set(self.order)) != len(self.order) or any(k not in chosen for k in self.order):
                raise ValueError("order must list chosen options, each once")
        if (self.max_m - self.min_m) / self.step_m * (len(chosen) + len(self.order or [])) > 400:
            raise ValueError("too many levels; use a bigger step_m")
        return self


class PlanIn(BaseModel):
    area_name: str = Field(min_length=1, max_length=80)
    place: str | None = Field(default=None, description="town id from GET /places, e.g. 'nadi'")
    summary: dict


def _clean(items: list[BaseModel]) -> list[dict]:
    # Drop missing optional values so the model falls back to its defaults.
    return [{k: v for k, v in i.model_dump().items() if v is not None} for i in items]


def _measures(m: Measures | None) -> dict:
    return m.model_dump(exclude_none=True) if m else {}


def _levels(lo: float, hi: float, step: float) -> list[float]:
    return [round(lo + i * step, 3) for i in range(round((hi - lo) / step) + 1)]


# --- endpoints -----------------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True, "llm_provider": llm.provider(), "llm_model": llm.model(), "mock": llm.is_mock()}


@app.get("/measures")
def measures():
    """The three options: how each is modelled, presets, assumption and evidence (show these in the app)."""
    return flood.MEASURES


@app.get("/places")
def list_places():
    """Every town set up in backend/places/ (name, map box, floor height, local context)."""
    return places.all_places()


@app.post("/flood")
def flood_at_level(body: FloodIn):
    """Impact at one flood level: baseline, with measures, and what the measures saved."""
    return flood.compare(body.level_m, _clean(body.buildings), _clean(body.facilities),
                         _clean(body.roads), _measures(body.measures))


@app.post("/hotspots")
def most_affected_areas(body: HotspotsIn):
    """The most affected areas at one river level, ranked by people with water inside their homes."""
    return hotspots.rank_areas(body.level_m, _clean(body.buildings), _clean(body.facilities), body.cell_m, body.top)


@app.post("/compare-measures")
def compare_measures(body: CompareIn):
    """The three options side by side (each alone vs doing nothing), plus optional layering in your order:
    what each step adds, and how every order compares."""
    return compare.compare_options(
        body.level_m, _measures(body.options), _clean(body.buildings), _clean(body.facilities), _clean(body.roads),
        _levels(body.min_m, body.max_m, body.step_m), body.target.model_dump(exclude_none=True) if body.target else None,
        body.order)


@app.post("/flood-curve")
def flood_curve(body: CurveIn):
    """People with water inside at each level, with and without measures (for the chart)."""
    levels = _levels(body.min_m, body.max_m, body.step_m)
    return {"levels": flood.curve(levels, _clean(body.buildings), _clean(body.facilities),
                                  _clean(body.roads), _measures(body.measures))}


@app.post("/flood-plan")
def flood_plan(body: PlanIn):
    """Plain-language plan from Gemini (or the built-in writer). Send /flood's response as `summary`."""
    try:
        if body.place and not places.get(body.place):
            raise HTTPException(status_code=404, detail=f"unknown place '{body.place}'")
        markdown, info = plan.write(body.area_name, body.summary, places.get(body.place))
    except llm.PlanError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"markdown": markdown, **info}