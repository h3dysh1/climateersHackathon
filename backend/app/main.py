"""FastAPI backend. Endpoints are defined in docs/contracts.md."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import claude_client, restoration

load_dotenv()

app = FastAPI(title="Restore to Protect API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Segment(BaseModel):
    id: str
    existing_width_m: float = Field(ge=0)
    restorable_width_m: float = Field(ge=0)
    restorable_ha: float = Field(ge=0, default=0)
    surge_people: float = Field(ge=0, default=0)


class ScenarioIn(BaseModel):
    restore_ids: list[str]
    segments: list[Segment]


class PlanIn(BaseModel):
    area_name: str
    summary: dict


@app.get("/health")
def health():
    return {"ok": True, "mock": claude_client.is_mock()}


@app.post("/scenario")
def scenario(body: ScenarioIn):
    return restoration.run_scenario([s.model_dump() for s in body.segments], body.restore_ids)


@app.post("/restoration-plan")
def restoration_plan(body: PlanIn):
    return {"markdown": claude_client.write_plan(body.area_name, body.summary)}
