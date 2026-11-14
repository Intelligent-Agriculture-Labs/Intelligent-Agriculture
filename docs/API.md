# API

Interactive docs: `http://localhost:8000/docs` (Swagger UI). Machine-readable spec: [`openapi.json`](openapi.json). TypeScript contract: [`../contracts/api.ts`](../contracts/api.ts).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, version, offline mode |
| GET | `/api/crops` | Crop table (id, family, type, N-fixing, root depth, season length) |
| GET | `/api/presets` | Demo farms (with `replay_date`) |
| POST | `/api/advice` | Weekly action cards + drought + water state + time series + sources |
| POST | `/api/simulate` | What-if: N past seasons for a scenario vs. baseline |
| POST | `/api/rotations` | Current rotation + ≥ 3 alternatives with metrics, calendar, texts |
| GET | `/api/climate?lat=&lon=` | 1984→ yearly indicators, trends, normals, insights |
| POST | `/api/terrain` | Computed terrain maps around the field (PNG overlays + legends + field stats + management zones) |
| GET | `/api/terrain/png/{key}/{layer}.png` | Map overlay image (web-mercator aligned with `bounds`) |
| POST | `/api/planner` | Season planner: sowing scan, stage dates, operations timeline, water budget, risk calendar |
| GET | `/api/export/advice.csv` | Tidy CSV of every series behind the advice |
| GET | `/api/export/field.geojson` | Point feature with the advice summary |

## Example
```bash
curl -s -X POST localhost:8000/api/advice -H 'content-type: application/json' -d '{
  "lat": 39.472, "lon": -118.777, "crop": "alfalfa", "planting_date": "2022-03-15",
  "irrigation": "flood", "lang": "en", "as_of": "2025-07-15"}'
```
Optional `FieldInput` fields:
- `last_irrigation_date`, `last_irrigation_mm`: sharpen the water balance;
- `water_allocation_mm`;
- `polygon`: `[[lon, lat], …]`, used for area;
- `as_of`: replay a past date.

## Errors
- `422`: invalid input (unknown crop, coordinates out of range).
- `503`: a data source is down and nothing is cached. The body explains which.
