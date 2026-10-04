# Nadi Flood Planner

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
4. **Measures:** Low / Medium / High settings for river channel clearing (0.1 / 0.25 / 0.5 m lower river),
   riverbank vegetation (2 / 5 / 10% lower river rise) and raising homes (50 / 100 / 250 homes by 1 m),
   from `backend/app/measures.json`, with sources and assumptions shown in the app. Picking a hotspot
   targets home-raising to a 200 m circle around it.
5. **Hotspots and plan:** the most affected areas are ranked, and an LLM (Gemini, or a built-in writer
   when no key is set) produces a plain-language plan.
6. **Mangroves (map layer):** current mangroves and mangroves lost since 1996 near the river mouth. They
   protect the coast from waves and erosion; they are not counted as lowering river floods.

## What we found (Nadi, model estimates)

All heights are metres the river rises above its normal level. Full tables: `docs/figures/results.md` and
`docs/checks/*.csv`; charts: `docs/figures/*.png`.

| River rise | Buildings reached | People reached |
| ---: | ---: | ---: |
| 2 m | 1,090 | about 1,300 |
| 3 m | 1,831 | about 2,200 |
| 4 m | 3,268 | about 6,100 |
| 6 m | 6,126 | about 14,700 |

- **The steepest rise is from 3 to 3.25 m** (about 1,900 more people reached), when water spills onto the
  flat floodplain.
- **Riverside villages are reached first.** Namotomoto is the most affected named community (about 390
  people reached at 2 m, 640 at 3 m); parts of Nawaka are reached from a 0.75 m rise. Sabeto Primary School
  is reached at 1.5 m, two town clinics at 3.75 m and Nadi Fire Station at 5.5 m. About 90% of buildings
  within 500 m of the town centre are reached by 6 m (median 5 m).
- **The best measure depends on flood size** (app's Medium settings: −0.25 m channel clearing, −5%
  vegetation, 100 homes raised by 1 m):

  | People kept dry | at 2 m | at 3 m | at 3.25 m |
  | --- | ---: | ---: | ---: |
  | *(people with water inside, no measure)* | *1,030* | *1,860* | |
  | Clear the river channel | 127 | 192 | 1,643 |
  | Riverbank vegetation | 80 | 85 | 1,509 |
  | Raise 100 homes | 435 | 475 | 613 |
  | All three together | 630 | 735 | |

  Raising homes wins at most flood sizes, but at 3.25 m, the edge of the floodplain, lowering the river by
  0.25 m keeps nearly three times as many people dry.
- **Check against reality:** Namotomoto and Nawaka are both named in flood reports from April 2016
  (Fiji Village) and March 2026 (Fiji Village, Fiji Sun).

Data size: 13,509 buildings, about 35,000 people (WorldPop) in mapped buildings, 46 facilities, 1,921 road
sections; 47% of buildings have an area name. Re-check every number with `python check_claims.py`.

## Repo layout

| Folder | Owner | What |
| --- | --- | --- |
| `frontend/` | P1 | React + MapLibre map and panels |
| `data-prep/` | P2 | Python: `fetch_osm.py`, `hand_flood.py` (flood data), `make_figures.py` (charts), `check_claims.py` (checks every pitch number), `00_pick_gmw_tile.py`, `03_coast_segments.py` (mangroves) |
| `backend/` | P3 | FastAPI: `/flood`, `/hotspots`, `/compare-measures`, `/flood-curve`, `/flood-plan` |
| `docs/` | All | `contracts.md` (file formats, units, API), `figures/` (charts, results), `checks/` (claim checks) |

**Rule:** work in your own folder; change `docs/contracts.md` only after agreeing in the team chat.

## Quick start

```bash
# Backend (built-in plan writer until GEMINI_API_KEY is set in backend/.env)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000             # try it at http://localhost:8000/docs
python -m pytest -q tests

# Frontend (Node 22); set VITE_API_URL=http://localhost:8000 in frontend/.env.local
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
# WorldPop: download fji_ppp_2020.tif into raw\ (hub.worldpop.org → Unconstrained individual countries 2000-2020, 100 m → Fiji → 2020)
# FABDEM: download S20E170-S10W180_FABDEM_V1-2.zip from data.bris.ac.uk, then:
python 00_pick_gmw_tile.py --zip raw\S20E170-S10W180_FABDEM_V1-2.zip --year fabdem --bbox 177.35 -17.88 177.55 -17.70
Move-Item raw\gmw_fabdem.tif raw\fabdem.tif -Force
python hand_flood.py --bbox 177.38 -17.86 177.52 -17.72 --dem raw\fabdem.tif --buildings raw\buildings_raw.geojson --rivers raw\rivers.geojson --facilities raw\facilities.geojson --roads raw\roads.geojson --places raw\places.geojson --worldpop raw\fji_ppp_2020.tif --area-max-km 3
python make_figures.py                                          # charts + results.md in docs\figures
python check_claims.py                                          # every pitch number vs the data, CSVs in docs\checks

# Mangrove layer (Global Mangrove Watch v3 zips from Zenodo record 6894273 in raw\):
python 00_pick_gmw_tile.py --zip raw\gmw_v3_2020_gtiff.zip --year 2020 --bbox 177.37 -17.86 177.52 -17.72
python 00_pick_gmw_tile.py --zip raw\gmw_v3_1996_gtiff.zip --year 1996 --bbox 177.37 -17.86 177.52 -17.72
python 03_coast_segments.py --bbox 177.37 -17.86 177.52 -17.72 --coastline raw\coastline.geojson --mangroves raw\gmw_2020.tif --restorable raw\gmw_1996.tif --earlier
```

Check `frontend/public/data/hand_summary.json` after each run. Run `--help` on any script for options.
Facilities are OSM amenities matched by whole name (hospital, clinic, doctors, school, kindergarten, college,
police, fire station, community centre, evacuation shelter) plus power substations; other OSM shelters
(mostly bus stops and carports) are skipped.

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
  not engineering designs. People kept dry is not value for money: 100 raised homes and a town-wide measure
  cost very different amounts.
- **Roads cut at 0.3 m** of water (shallow moving water can float a car).
- **Area names** are the nearest OSM place within 3 km, so "Namotomoto" covers more than the village itself.
- **OSM gaps.** Missing rivers, bridges, facilities or place names lead to wrong cuts, missed facilities or
  unnamed hotspots.
- **Mangroves** reduce waves and erosion on the coast (13–66% wave height reduction per 100 m in field
  studies) but have a negligible effect on river flood levels (HESS 2024), so they are not in the flood model.

## Tools and data used (required for submission)

**Datasets**
- FABDEM V1-2 bare-earth elevation (Hawker et al. 2022, University of Bristol), CC BY-NC-SA 4.0, non-commercial
- Copernicus DEM GLO-30 (ESA/Copernicus), used for comparison
- Overture Maps buildings (ODbL / CDLA by source; includes OpenStreetMap, Microsoft and Google footprints)
- OpenStreetMap rivers, facilities, roads, place names and coastline via the Overpass API (© OpenStreetMap contributors, ODbL)
- WorldPop Fiji 2020 population counts, 100 m, unconstrained (CC BY 4.0)
- Global Mangrove Watch v3, mangrove extent 1996 and 2020 (Bunting et al. 2022), CC BY 4.0
- Basemap: CARTO dark (© OpenStreetMap contributors, © CARTO)

**Evidence used in the model**
- Measures: sources listed per option in `backend/app/measures.json`
- Mangroves: wave reduction 13–66% per 100 m (McIvor et al. 2012); negligible effect on riverine floods
  (Hydrology and Earth System Sciences, 2024, "Mangroves as nature-based mitigation for ENSO-driven compound flood risks")
- Context: Nadi flood history (2009 flood figures), Nadi Flood Alleviation Project (AIFFP, ADB)
- Validation: flood reports from Fiji Village (6 Apr 2016; 4 Mar 2026) and Fiji Sun (4 Mar 2026)

**APIs and services**
- Google Gemini API (`gemini-2.5-flash`) for the plan text, with a built-in writer as fallback
- Overpass API (OpenStreetMap data)
- Hosting: Vercel (frontend and FastAPI backend as Vercel Services)

**Libraries**
- Frontend: React, Vite, MapLibre GL JS
- Backend: FastAPI, Uvicorn, pydantic, httpx, python-dotenv
- Data: numpy, scipy, pandas, geopandas, shapely, rasterio, requests, matplotlib, overturemaps

**AI assistance**
- Claude (claude.ai) was used for idea development, planning, writing and testing the data-prep scripts
  (`hand_flood.py`, `fetch_osm.py`, `make_figures.py`, `check_claims.py`, `00_pick_gmw_tile.py`,
  `03_coast_segments.py`), reviewing the code for bugs, and drafting the README and submission text.
  All numbers were re-checked against the data with `check_claims.py`.
- Google Gemini writes the plan text inside the app.
- List any other AI tools each team member used: [P1: ...] [P3: ...]

## Team

| Role | Name |
| --- | --- |
| P1: Map and experience | Jess |
| P2: Data and evidence | Chris |
| P3: AI and backend | Hedy |

All work was created during Climate Hack-tion (from 9:00am AEST, Fri 2 Oct 2026).
