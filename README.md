# Nadi Flood Planner (working title)

See who floods in Nadi, Fiji, as the river rises, and compare the planning measures that keep the most
people dry before the next wet season: clearing the river channel, raising homes, and riverbank vegetation.
Turns the result into a plain-language plan for Nadi Town Council, communities and government agencies.

Built for Climate Hack-tion 2026 · Build for 2035 · COP31 priorities: **Resilient Cities & Buildings**
(coping with climate extremes) and **Awareness Across All Areas**.

## Why Nadi

Nadi floods almost every year: 26 major floods since 1991, and the January 2009 flood killed 11 people,
left 12,000 homeless and caused FJD 113 million in damage. Australia (AIFFP) and the ADB are funding the
Nadi Flood Alleviation Project, so there is a real decision about where and how to reduce flood risk.

## How it works

1. **Height above the river:** for every 30 m patch of ground, how many metres it sits above the river or
   sea it drains to (HAND, height above nearest drainage), from bare-earth elevation (FABDEM).
2. **Who floods as the river rises:** the water is raised in 0.25 m steps; a patch floods only once water
   connected to the river or sea can reach it (hollows behind banks stay dry until the water tops them).
3. **Homes, facilities and roads:** each building, clinic, school, substation and road section gets the
   river rise at which water first reaches it; people per building come from WorldPop.
4. **Measures:** what-if sliders for river channel clearing, raising homes and riverbank vegetation
   (`backend/app/measures.json`, with sources and assumptions shown in the app).
5. **Hotspots and plan:** the most affected areas are ranked, and an LLM (or a built-in writer) produces a
   plain-language plan.
6. **Mangroves (map layer):** current mangroves and mangroves lost since 1996 near the river mouth. They
   protect the coast from waves and erosion; they are not counted as lowering river floods.

## Repo layout

| Folder | Owner | What |
| --- | --- | --- |
| `frontend/` | P1 | React + MapLibre + deck.gl map and panels |
| `data-prep/` | P2 | Python: `fetch_osm.py`, `hand_flood.py` (flood data), `00_pick_gmw_tile.py`, `03_coast_segments.py` (mangroves) |
| `backend/` | P3 | FastAPI: `/flood`, `/hotspots`, `/compare-measures`, `/flood-curve`, `/flood-plan` |
| `docs/` | All | `contracts.md` (file formats, units, API) |

**Rule:** work in your own folder; change `docs/contracts.md` only after agreeing in the team chat.

## Quick start

```bash
# Backend (built-in plan writer until GEMINI_API_KEY is set in backend/.env)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000             # try it at http://localhost:8000/docs
python -m pytest -q tests

# Frontend (Node 22)
cd ../frontend
npm install
npm run dev                                           # http://localhost:5173
```

## Data pipeline (P2)

From `data-prep/` (Windows PowerShell shown; use `/` paths on Mac/Linux). Large inputs go in
`data-prep/raw/`, which is not committed.

```powershell
pip install -r requirements.txt
python fetch_osm.py --bbox 177.38 -17.86 177.52 -17.72          # rivers, facilities, roads, place names
overturemaps download "--bbox=177.38,-17.86,177.52,-17.72" -f geojson --type=building -o raw\buildings_raw.geojson
# WorldPop: download fji_ppp_2020.tif into raw\ (hub.worldpop.org → Population Counts → Fiji → 2020)
# FABDEM: download S20E170-S10W180_FABDEM_V1-2.zip from data.bris.ac.uk, then:
python 00_pick_gmw_tile.py --zip raw\S20E170-S10W180_FABDEM_V1-2.zip --year fabdem --bbox 177.35 -17.88 177.55 -17.70
Move-Item raw\gmw_fabdem.tif raw\fabdem.tif -Force
python hand_flood.py --bbox 177.38 -17.86 177.52 -17.72 --dem raw\fabdem.tif --buildings raw\buildings_raw.geojson --rivers raw\rivers.geojson --facilities raw\facilities.geojson --roads raw\roads.geojson --places raw\places.geojson --worldpop raw\fji_ppp_2020.tif --area-max-km 3

# Mangrove layer (Global Mangrove Watch v3 zips from Zenodo record 6894273 in raw\):
python 00_pick_gmw_tile.py --zip raw\gmw_v3_2020_gtiff.zip --year 2020 --bbox 177.37 -17.86 177.52 -17.72
python 00_pick_gmw_tile.py --zip raw\gmw_v3_1996_gtiff.zip --year 1996 --bbox 177.37 -17.86 177.52 -17.72
python 03_coast_segments.py --bbox 177.37 -17.86 177.52 -17.72 --coastline raw\coastline.geojson --mangroves raw\gmw_2020.tif --restorable raw\gmw_1996.tif --earlier
```

Check `frontend/public/data/hand_summary.json` after each run. Run `--help` on any script for options.

## Results for Nadi (current run)

From `frontend/public/data/hand_summary.json`: 13,509 buildings, about 35,000 people (WorldPop), 63 critical
facilities and 1,933 road sections in the map box.

| River rise | Buildings reached | People reached |
| --- | --- | --- |
| 1 m | 574 | about 1,000 |
| 2 m | 1,199 | about 1,700 |
| 3 m | 1,912 | about 2,600 |
| 4 m | 3,327 | about 6,300 |
| 5 m | 4,828 | about 10,500 |
| 6 m | 6,155 | about 14,700 |

"Reached" means floodwater gets to the building; the app also shows how many have water **inside**
(above the assumed floor height). These are planning estimates, not predictions of a specific flood.
Robustness check: an independent, simpler version of the model (main river only) gave the same order of
magnitude (about 640 buildings at 2 m and 1,530 at 3 m).
Sense check against history: within about 500 m of Nadi town centre, 434 of 483 buildings (90%) are reached
within a 6 m rise, at a median of 5 m. So the model has the town centre flooding in large floods rather than
every year, consistent with major events such as the January and March 2012 floods, which inundated the town.

## Assumptions and limits (also in the app's About panel)

- **Not a flow simulation.** HAND shows which ground the river reaches as it rises. It ignores rainfall,
  timing, flow speed and how a flood moves down the valley.
- **Simplified drainage.** Each patch uses the nearest mapped river, stream or sea at or below its own height
  (straight-line distance, not traced flow paths); unmapped channels are not detected.
- **Elevation error.** FABDEM is a 30 m global model; heights can be off by a metre or more, especially in
  dense town blocks. We compared it with Copernicus DEM: FABDEM sits between the two Copernicus variants.
- **People are estimated.** WorldPop 2020 people are shared across buildings by footprint area. About half of
  WorldPop's residents in the map box fall in 100 m cells with no mapped building, so they are not counted.
- **Floor height is assumed:** 0.3 m for every home (`backend/places/nadi.json`, from Fiji's 2017 census mix
  and building guidelines). Surveyed floor heights would replace it.
- **Measures are what-ifs.** Channel clearing and vegetation effects are user assumptions with sourced ranges,
  not engineering designs.
- **Roads cut at 0.3 m** of water (shallow moving water can float a car).
- **OSM gaps.** Missing rivers, bridges, facilities or place names lead to wrong cuts, missed facilities or
  unnamed hotspots.
- **Area names.** Each building takes the nearest OpenStreetMap place name within 3 km; 6,414 of 13,509
  buildings (47%) get one. Below the backend's 80% threshold, hotspots are grouped on a 250 m grid instead.
- **Mangroves** reduce waves and erosion on the coast (13–66% wave height reduction per 100 m in field
  studies) but have a negligible effect on river flood levels (HESS 2024), so they are not in the flood model.

## Tools and data used (required for submission)

**Datasets**
- FABDEM V1-2 bare-earth elevation (Hawker et al. 2022, University of Bristol), CC BY-NC-SA 4.0, non-commercial
- Copernicus DEM GLO-30 (ESA/Copernicus), used for comparison
- Overture Maps buildings (ODbL / CDLA by source; includes OpenStreetMap, Microsoft and Google footprints)
- OpenStreetMap rivers, facilities, roads, place names and coastline via the Overpass API (© OpenStreetMap contributors, ODbL)
- WorldPop Fiji 2020 population counts, 100 m (CC BY 4.0)
- Global Mangrove Watch v3, mangrove extent 1996 and 2020 (Bunting et al. 2022), CC BY 4.0
- Basemap: CARTO (© OpenStreetMap contributors, © CARTO)

**Evidence used in the model**
- Measures: sources listed per option in `backend/app/measures.json`
- Mangroves: wave reduction 13–66% per 100 m (McIvor et al. 2012); negligible effect on riverine floods
  (Hydrology and Earth System Sciences, 2024, "Mangroves as nature-based mitigation for ENSO-driven compound flood risks")
- Context: Nadi flood history (2009 flood figures), Nadi Flood Alleviation Project (AIFFP, ADB)

**APIs and services**
- Google Gemini API (`gemini-2.5-flash`) for the plan text, with a built-in writer as fallback
- Overpass API (OpenStreetMap data)
- Hosting: Vercel (frontend), Render (backend)

**Libraries**
- Frontend: React, Vite, MapLibre GL JS, deck.gl, react-map-gl
- Backend: FastAPI, Uvicorn, pydantic, httpx, python-dotenv
- Data: numpy, scipy, pandas, geopandas, shapely, rasterio, pyproj, requests, overturemaps

**AI assistance**
- Claude (claude.ai) was used for idea development, planning, and writing and testing the data-prep scripts
  (`hand_flood.py`, `fetch_osm.py`, `00_pick_gmw_tile.py`, `03_coast_segments.py`).
- List any other AI tools each team member used: [P1: ...] [P3: ...]

## Team

| Role | Name |
| --- | --- |
| P1: Map and experience | |
| P2: Data and evidence | |
| P3: AI and backend | |

All work was created during Climate Hack-tion (from 9:00am AEST, Fri 2 Oct 2026).
