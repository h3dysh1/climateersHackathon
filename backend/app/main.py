"""FastAPI backend. Endpoints are defined in docs/contracts.md."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import claude_client, scoring

load_dotenv()

app = FastAPI(title="Cyclone Prepare API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ClassifyIn(BaseModel):
    id: str
    image_base64: str
    media_type: str = "image/png"


class Building(BaseModel):
    id: str
    exposure: float = Field(ge=0, le=1)
    vulnerability: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    band: str


class PlanUpgradesIn(BaseModel):
    budget: int = Field(ge=0)
    buildings: list[Building]


class ResiliencePlanIn(BaseModel):
    area_name: str
    summary: dict


@app.get("/health")
def health():
    return {"ok": True, "mock": claude_client.is_mock()}


@app.post("/classify")
def classify(body: ClassifyIn):
    if len(body.image_base64) > 7_000_000:
        raise HTTPException(413, "Image too large; send a small tile (~256 px).")
    return {"id": body.id, **claude_client.classify_roof(body.image_base64, body.media_type, body.id)}


@app.post("/plan-upgrades")
def plan_upgrades(body: PlanUpgradesIn):
    return scoring.plan_upgrades([b.model_dump() for b in body.buildings], body.budget)


@app.post("/resilience-plan")
def resilience_plan(body: ResiliencePlanIn):
    return {"markdown": claude_client.write_plan(body.area_name, body.summary)}
