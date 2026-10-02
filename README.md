# Restore to Protect (working title)

Find where restoring coastal mangroves would protect the most people from cyclone waves in Lautoka, Fiji, and turn it into a plan a city council can act on.

Built for Climate Hack-tion 2026 · Build for 2035 · COP31 priority: **Resilient Cities & Buildings** (nature-based protection from climate extremes).

## How it works

1. **Coast segments:** the coastline is split into ~500 m segments; for each, we measure today's mangrove width and how much could be restored (mangroves lost since 1996).
2. **People behind:** buildings and people within 1 km of each segment, and how many sit in the storm-surge zone.
3. **Protection model:** a conservative wave-reduction model from published field ranges (13% per 100 m of mangroves, capped at 66%; surge reduction is small).
4. **Restoration scenario:** pick sites (or "top 3 / top 10") and see how many people move from "no buffer" to better protection, and how many hectares that takes.
5. **Evidence:** compare Cyclone Winston damage behind mangroves vs without (real survey data).
6. **Restoration plan:** an LLM writes a plain-language plan for council and community meetings.

## Repo layout

| Folder | Owner | What |
| --- | --- | --- |
| `frontend/` | P1 | React + MapLibre + deck.gl map and panels |
| `data-prep/` | P2 | Python pipeline: track, buildings, coast segments, people behind, validation |
| `backend/` | P3 | FastAPI: `/scenario`, `/restoration-plan` |
| `docs/` | All | `contracts.md` (shared file formats, API and the restoration model) |

**Rule:** work in your own folder; change `docs/contracts.md` only after agreeing in the team chat.

## Quick start

```bash
# 1. Mock data so everyone can start now (writes to frontend/public/data/; needs only Python)
cd data-prep
python make_mock_data.py

# 2. Backend (MOCK mode until you add ANTHROPIC_API_KEY)
cd ../backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000           # check http://localhost:8000/health
python -m pytest -q tests

# 3. Frontend (Node 22)
cd ../frontend
npm install
npm run dev                                         # http://localhost:5173
```

If the backend is down, the frontend runs scenarios locally with the same model.

## Real-data pipeline (P2), in order

```bash
cd data-prep
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python 01_track.py --ibtracs raw/ibtracs.SP.list.v04r01.csv
overturemaps download --bbox=177.40,-17.67,177.50,-17.57 -f geojson --type=building -o raw/buildings_raw.geojson
python 02_buildings.py --input raw/buildings_raw.geojson --bbox 177.40 -17.67 177.50 -17.57 --max 5000
python 03_coast_segments.py --coastline raw/coastline.geojson --mangroves raw/gmw_2020.geojson --restorable raw/gmw_1996.geojson --earlier
python 04_people_behind.py
python 05_validate.py --damage raw/2016TCWinston_DamageData.csv --show-columns   # then run with column names
```

Download sources are listed in the team doc's **Data pipeline** tab. Run `--help` on any script.

## Tools and data used (keep this updated — required for submission)

**Datasets**
- [ ] Global Mangrove Watch v3 (mangrove extent 1996 and 2020), CC BY 4.0
- [ ] Overture Maps buildings (ODbL; includes OpenStreetMap, Microsoft and Google footprints)
- [ ] OpenStreetMap coastline (© OpenStreetMap contributors, ODbL)
- [ ] WorldPop Fiji population counts (CC BY 4.0) — if used for people per building
- [ ] FABDEM V1-2 elevation (CC BY-NC-SA 4.0) — if used for surge zones
- [ ] IBTrACS v04 (NOAA) — Cyclone Winston track
- [ ] Wind damage dataset for buildings from 2016 TC Winston (Paulik et al., Zenodo 10.5281/zenodo.14353428)
- [ ] Basemap: CARTO Dark Matter (© OpenStreetMap contributors, © CARTO)

**Evidence used in the model**
- Wave reduction 13–66% over 100 m of mangroves (McIvor et al. 2012, via published reviews)
- Surge reduction 0–0.25 m per km of mangroves (field observations summarised in PMC10995189)

**APIs and services**
- [ ] Claude API (Anthropic) — restoration plan writing
- [ ] Hosting: Vercel (frontend), Render (backend)

**Libraries**
- Frontend: React, Vite, MapLibre GL JS, deck.gl, react-map-gl
- Backend: FastAPI, Uvicorn, anthropic, pydantic
- Data: pandas, numpy, geopandas, shapely, rasterio, scipy, overturemaps

**AI assistance**
- [ ] Project planning and this starter scaffold were generated with Claude (claude.ai) during the hackathon
- [ ] List any AI coding tools each team member uses

## Team

| Role | Name |
| --- | --- |
| P1 — Map and experience | |
| P2 — Data and evidence | |
| P3 — AI and backend | |

All work was created during Climate Hack-tion (from 9:00am AEST, Fri 2 Oct 2026).
