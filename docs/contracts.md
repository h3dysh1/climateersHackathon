# Shared contracts

Change only after posting in the team chat. All data files live in `frontend/public/data/`.

## Restoration model (shared by data-prep, backend and frontend — change all three together)

- Wave height reduction = **13% per 100 m** of mangrove width (low end of the 13–66% field range), **capped at 66%**
- Storm-surge reduction = **0.1 m per km** of mangrove width (observed range 0–0.25 m/km; small, so the main benefit is waves and erosion)
- Protection band from wave reduction: `strong` ≥ 40%, `partial` ≥ 20%, else `exposed`
- Restoring a segment adds its `restorable_width_m` to its `existing_width_m`

## Files

### `coast_segments.geojson` (P2 → P1, P3)
LineStrings (~500 m each). Properties:
```json
{"id": "s013", "length_m": 500, "existing_width_m": 80, "restorable_width_m": 300, "restorable_ha": 15.0,
 "people_behind": 140, "surge_people": 101, "buildings_behind": 32,
 "wave_reduction_now": 0.104, "wave_reduction_restored": 0.494, "surge_reduction_restored_m": 0.038,
 "band_now": "exposed", "band_restored": "strong", "priority": 2.63}
```
`priority` = surge-exposed people behind × added wave reduction ÷ restorable hectares (people protected per hectare; restore highest first).

### `mangroves.geojson` (P2 → P1)
Current mangrove extent polygons (Global Mangrove Watch).

### `buildings.geojson` (P2 → P1)
Points: `{"id": "b0001", "segment_id": "s013", "people": 4, "surge_m": 1, "coast_m": 240}`. `surge_m` is null outside the surge zone; `segment_id` is null if more than 1 km from the coast.

### `surge_zones.geojson` (P2, optional input to `04_people_behind.py`)
Polygons with `level_m` (1, 2, 3).

### `track.json` (P2 → P1)
`[{"time": "2016-02-20T06:00:00Z", "lat": -17.3, "lon": 178.3, "wind_kt": 155, "category": 5}]`

### `validation.json` (P2 → P1)
```json
{"records": 120, "near_mangroves": 38, "no_mangroves": 60,
 "severe_rate_with_mangroves": 0.21, "severe_rate_without": 0.34, "note": "..."}
```

## API (P3, FastAPI)

| Method + path | Request | Response |
| --- | --- | --- |
| `GET /health` | – | `{"ok": true, "mock": bool}` |
| `POST /scenario` | `{"restore_ids": ["s013"], "segments": [{id, existing_width_m, restorable_width_m, restorable_ha, surge_people}]}` | `{"restored", "hectares", "people_better_protected", "before": {band: people}, "after": {...}, "segments": [{id, width_m, wave_reduction, surge_reduction_m, band, restored}]}` |
| `POST /restoration-plan` | `{"area_name": "Lautoka", "summary": {...}}` | `{"markdown": "..."}` |
