# Shared contracts

Change only after posting in the team chat. All data files live in `frontend/public/data/` and are
written by `data-prep/hand_flood.py` (flood data) and `data-prep/03_coast_segments.py` (mangrove layer).

## Units (everyone)

- Every height is **metres above the normal river or sea level**, the same unit as the app's slider
  ("how far the river rises").
- `99` means water never reaches it within the modelled range (6 m).
- `ground_m` is **HAND** (height above nearest drainage), not ground elevation above sea level.
  Label it "height above river" in the app.

## Flood data files (P2 → P1, P3)

### `buildings.json`
A JSON **list**, one entry per building (max 15,000; every building water can reach is always kept):
```json
{"id": "b00042", "lon": 177.4431, "lat": -17.7962, "ground_m": 1.2, "floods_at_m": 1.5,
 "people": 3.84, "type": "home", "area": "Namotomoto"}
```
- `floods_at_m`: river rise at which floodwater connected to the river/sea first reaches the building.
- `people`: WorldPop 2020 people shared across the buildings in each 100 m cell by footprint area.
- `area`: nearest OSM place name within the search distance; **omitted** when there is none.

### `facilities.json`
List: `{"id": "f0007", "name": "Nadi Hospital", "type": "hospital", "lon": ..., "lat": ..., "ground_m": 2.1, "floods_at_m": 2.25, "area": "..."}`.
`type` is the OSM `amenity` (hospital, clinic, doctors, school, community_centre, fire_station, police...) or `substation`.
Shelters are included only if tagged as evacuation shelters. `name` and `area` may be null/omitted.

### `roads.json`
List of road sections (max 500 m): `{"id": "r00123", "name": "Queens Road", "low_point_m": 0.75, "length_m": 480}`.
`low_point_m` = lowest height water must reach along the section; bridges and samples on the river channel are skipped.
The backend treats a section as cut when `level_m − low_point_m ≥ 0.3` (`impassable_depth_m`).

### `roads.geojson`
The same sections as LineStrings (same `id`, `name`, `low_point_m`, `length_m`), for drawing.

### `flood_extents.geojson`
Water outline every 0.5 m (0.5 → 6 m). MultiPolygons with property `level_m`. **Cumulative**: for slider
value L, draw the feature with the largest `level_m` ≤ L.

### `rivers.geojson`
The waterways used as drainage. LineStrings with property `waterway` (`river`, `stream`, `canal`, `drain`).

### `hand_summary.json`
Run settings and sanity checks (buildings and people reached at 1–6 m, people source, area-name coverage,
facilities, road sections). For the team and README, not loaded by the app.

## Mangrove layer (P2 → P1; display and narrative only)

Mangroves protect the **coast** from waves and erosion. They do **not** lower river floods, so they are not
part of the flood calculations. Shown as a map layer with this simple, conservative model:

- Wave height reduction = **13% per 100 m** of mangrove width (low end of the 13–66% field range), capped at 66%
- Protection band: `strong` ≥ 40%, `partial` ≥ 20%, else `exposed`

### `mangroves.geojson`
Current mangrove extent polygons (Global Mangrove Watch v3, 2020).

### `restorable.geojson`
Mangrove area lost since 1996 (Global Mangrove Watch), patches of at least 0.25 ha.

### `coast_segments.geojson`
LineStrings (~500 m of coast). Properties used by the map:
`id`, `length_m`, `existing_width_m`, `existing_ha`, `restorable_width_m`, `restorable_ha`,
`wave_reduction_now`, `wave_reduction_restored`, `band_now`, `band_restored`.

## API (P3, FastAPI; full schemas at `/docs`)

The frontend loads `buildings.json`, `facilities.json` and `roads.json` and sends them in the request body.

| Method + path | Request | Response |
| --- | --- | --- |
| `GET /health` | – | `{"ok": true, "llm_provider", "llm_model", "mock"}` |
| `GET /measures` | – | The three options from `backend/app/measures.json` (how, presets, assumption, evidence, sources) |
| `GET /places` | – | Town settings from `backend/places/*.json` (e.g. `nadi`: bbox, floor height, existing work) |
| `POST /flood` | `{level_m, buildings, facilities, roads, measures?}` | `{baseline, with_measures, saved, measures}` |
| `POST /hotspots` | `{level_m, buildings, facilities, cell_m?, top?}` | Most affected areas (by name if ≥80% of buildings have `area`, else a 250 m grid) |
| `POST /compare-measures` | `{level_m, buildings, facilities, roads, options, order?, target?}` | Each option alone vs nothing, plus layering |
| `POST /flood-curve` | `{buildings, facilities, roads, measures?, min_m, max_m, step_m}` | People with water inside at each level, with and without measures |
| `POST /flood-plan` | `{area_name, place?, summary}` | `{"markdown": ...}` plain-language plan |

`measures` = `{"channel_clearing_m": 0.25, "nature_based": {"reduction_pct": 5}, "raise_homes": {"count": 100, "height_m": 1.0, "target": {...}}}` (any can be left out).

## Removed (cyclone/mangrove-restoration version)

`track.json`, `validation.json`, `buildings.geojson`, `surge_zones.geojson`, `flood_levels.json`,
`flood_zones.geojson`, `POST /scenario`, `POST /restoration-plan`. Do not use them.
