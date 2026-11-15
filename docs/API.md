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
| POST | `/api/solar-pump` | Solar PV irrigation pump sizing: NASA POWER irradiance + FAO-56 peak water need → kWp, pump flow, kWh/m³, USD/m³ vs diesel, CO₂ avoided (`SolarPumpRequest` → `SolarPumpResponse` in `contracts/api.ts`) |
| GET | `/api/climate?lat=&lon=` | 1984→ yearly indicators, trends, normals, insights |
| POST | `/api/terrain` | Computed terrain maps around the field (PNG overlays + legends + field stats + management zones) |
| GET | `/api/terrain/png/{key}/{layer}.png` | Map overlay image (web-mercator aligned with `bounds`) |
| POST | `/api/planner` | Season planner: sowing scan, stage dates, operations timeline, water budget, risk calendar; rain-fed tropical fields: `rain_season` limits and `onset_ok` per scanned date |
| GET | `/api/rain-season?lat=&lon=&crop=&as_of=&lang=` | Rainy-season onset/cessation climatology since 1984, false-start odds, trends, this season's status, sowing windows per crop, and the `rain_onset` card (`RainSeasonResponse`) |
| POST | `/api/fields/detect` | Tap-to-detect: editable field polygon around a point (sub-metre imagery) |
| POST | `/api/satellite` | Sentinel-2 field analysis (async; poll until `status: done`): NDVI series, phenology, AI zones, Kcb, latest images |
| GET | `/api/satellite/png/{key}/{zones,ndvi,truecolor}.png` | Satellite overlays aligned with `bounds` |
| POST | `/api/farms` · POST `/api/farms/join` · GET/PUT `/api/farms/{farm_id}` | Account-free farm sync between devices |
| POST | `/api/auth/register` · `/api/auth/login` · `/api/auth/logout` · GET `/api/auth/me` · POST `/api/auth/password` · DELETE `/api/auth/me` | Accounts (Bearer token) |
| GET / PUT | `/api/me/farm` | The account's farm (fields, plans, settings), merged per field |
| POST | `/api/rotations/plan` | Per-field multi-year rotation plan: per-year biological + agronomic check, suggestions, optimised plan |
| GET | `/api/glossary?lang=` | Plain-language explanations of the app's terms |
| POST | `/api/advice/text?name=&max_chars=320&max_parts=2` | This week's advice as SMS/WhatsApp text in the farmer's language. Latin scripts are normalised to the GSM-7 alphabet; the least urgent cards are dropped until it fits `max_parts` SMS (GSM 03.38 part sizes: 160/153 GSM-7, 70/67 UCS-2) |
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
