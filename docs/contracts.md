# Shared contracts

Agree these by Friday 4pm. Change only after posting in the team chat. All data files live in `frontend/public/data/`.

## Files

### `track.json` (P2 → P1)
```json
[{"time": "2016-02-20T06:00:00Z", "lat": -17.3, "lon": 178.3, "wind_kt": 150, "category": 5}]
```
Longitudes stay in −180..180 for the map; `data-prep` handles the 180° meridian internally.

### `buildings.geojson` (P2 → P1, P3)
GeoJSON FeatureCollection of Points. Properties:
```json
{"id": "b0001", "village": "Rakiraki", "tile": "tiles/b0001.png"}
```

### `roof_labels.json` (P3 → P2)
```json
{"b0001": {"roof_material": "corrugated_iron", "roof_shape": "gable", "condition": "fair", "confidence": 0.8}}
```
Allowed values:
- `roof_material`: `corrugated_iron` | `concrete` | `tile` | `thatch` | `timber` | `unknown`
- `roof_shape`: `gable` | `hip` | `flat` | `skillion` | `unknown`
- `condition`: `good` | `fair` | `poor` | `damaged` | `unknown`
- `confidence`: 0–1

### `risk.json` (P2 → P1, P3)
```json
{"buildings": [{"id": "b0001", "exposure": 0.82, "vulnerability": 0.65, "risk": 0.53, "band": "high"}]}
```
- `risk = exposure × vulnerability` (both 0–1)
- `band`: `high` if risk ≥ 0.5, `medium` if ≥ 0.25, else `low`

### `validation.json` (P2 → P1)
```json
{
  "n_test": 210,
  "severe_damage_test": 64,
  "model_recall_severe": 0.72,
  "baseline_recall_severe": 0.55,
  "model_precision_high": 0.48,
  "note": "Held-out 30% of survey records; severe = damage state DS2–DS3."
}
```

## API (P3, FastAPI)

| Method + path | Request | Response |
| --- | --- | --- |
| `GET /health` | – | `{"ok": true, "mock": bool}` |
| `POST /classify` | `{"id": "b0001", "image_base64": "...", "media_type": "image/png"}` | one `roof_labels` entry + `"id"` |
| `POST /plan-upgrades` | `{"budget": 50, "buildings": [risk.json entries]}` | `{"upgraded": [ids], "before": {"high":n,"medium":n,"low":n}, "after": {...}, "buildings": [re-scored entries]}` |
| `POST /resilience-plan` | `{"area_name": "...", "summary": {...}}` | `{"markdown": "..."}` |

Upgrade rule (shared by backend and frontend fallback): an upgraded building's `vulnerability` is multiplied by **0.5**, then risk and band are recomputed.
