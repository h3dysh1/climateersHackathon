# Cyclone Prepare (working title)

Find the buildings most likely to fail in the next cyclone, prove it against Cyclone Winston (Fiji, 2016), and show which upgrades protect the most people.

Built for Climate Hack-tion 2026 · Build for 2035 · COP31 priority: **Resilient Cities & Buildings**.

## How it works

1. **Roof scan:** each building's image tile is classified by a vision-capable LLM (roof material, shape, condition).
2. **Risk score:** risk = Winston wind exposure × roof vulnerability.
3. **Validation:** predicted high-risk buildings are compared with real Winston damage survey records (held-out 30%).
4. **Upgrade planner:** choose a budget ("upgrade 50 homes") and see buildings move out of the high-risk band.
5. **Resilience plan:** an LLM writes a plain-language one-page plan from the results.

## Repo layout

| Folder | Owner | What |
| --- | --- | --- |
| `frontend/` | P1 | React + MapLibre + deck.gl map and panels |
| `data-prep/` | P2 | Python scripts: track, buildings, tiles, risk, validation |
| `backend/` | P3 | FastAPI: `/classify`, `/plan-upgrades`, `/resilience-plan` |
| `docs/` | All | `contracts.md` (shared file and API formats) |

**Rule:** work in your own folder; change `docs/contracts.md` only after agreeing in the team chat.

## Quick start

```bash
# 1. Mock data so everyone can start now (writes to frontend/public/data/)
cd data-prep
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python make_mock_data.py

# 2. Backend (runs in MOCK mode with no API key)
cd ../backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env          # add ANTHROPIC_API_KEY when ready
uvicorn app.main:app --reload --port 8000
# check: http://localhost:8000/health

# 3. Frontend
cd ../frontend
npm install
npm run dev                      # http://localhost:5173
```

The frontend reads `public/data/*.json` and calls the backend at `VITE_API_URL` (default `http://localhost:8000`). If the backend is down, the upgrade planner falls back to a local calculation so the map still works.

## Data pipeline (P2), in order

```bash
cd data-prep
python 01_track.py --ibtracs path/to/ibtracs.SP.list.v04r01.csv        # → track.json
python 02_buildings.py --input path/to/buildings.geojson --bbox ...     # → buildings.geojson
python 03_tiles.py --image path/to/oam_image.tif                        # → frontend/public/tiles/<id>.png
python 04_risk.py                                                       # → risk.json (needs roof_labels.json from backend)
python 05_validate.py --damage path/to/2016TCWinston_DamageData.csv     # → validation.json
```

Each script prints `--help`. Outputs go to `frontend/public/data/` (and tiles to `frontend/public/tiles/`).

## Tools and data used (keep this updated — required for submission)

**Datasets**
- [ ] IBTrACS v04 (NOAA) — Cyclone Winston track
- [ ] Wind damage dataset for buildings from 2016 TC Winston (Paulik et al., Zenodo 10.5281/zenodo.14353428)
- [ ] OpenAerialMap imagery (CC-BY 4.0, Open Imagery Network contributors) — confirm the exact image used
- [ ] Building footprints: _which source?_
- [ ] Basemap: CARTO Dark Matter (© OpenStreetMap contributors, © CARTO)

**APIs and services**
- [ ] Claude API (Anthropic) — roof classification (vision) and resilience plan writing
- [ ] Hosting: Vercel (frontend), Render (backend)

**Libraries**
- Frontend: React, Vite, MapLibre GL JS, deck.gl, react-map-gl
- Backend: FastAPI, Uvicorn, anthropic, pydantic
- Data: pandas, numpy, geopandas, shapely, rasterio, Pillow

**AI assistance**
- [ ] Project planning and this starter scaffold were generated with Claude (claude.ai) during the hackathon
- [ ] List any AI coding tools each team member uses

## Team

| Role | Name |
| --- | --- |
| P1 — Map and experience | |
| P2 — Data and validation | |
| P3 — AI and backend | |

All work was created during Climate Hack-tion (from 9:00am AEST, Fri 2 Oct 2026).
