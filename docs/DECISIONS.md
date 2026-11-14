# Decisions (ADRs)

Format: decision · alternatives · reason. Newest at the bottom. Times are CET (Europe/Berlin).

## ADR-001 Settings not provided in the build prompt (2026-11-14 15:45)
- **Deadline:** Sunday 2026-11-15 23:59 local time. This is the official Space Apps submission deadline from the Judging & Awards Guide; the team's local event is assumed to be in Europe/Berlin.
- **Name:** *FieldShift*. It comes from the repo README and matches the challenge title "Field Shift".
- **Demo region:** Lahontan Valley (Fallon), Nevada, with irrigated alfalfa. The challenge's hero photo shows a Nevada alfalfa farmer. The region has severe, well-documented drought and water-delivery cuts and good NASA data coverage, and alfalfa is the classic "rotation question" crop. Three secondary presets show global reach: Machakos, Kenya (rain-fed smallholder maize); Córdoba, Spain (rain-fed wheat/sunflower after the 2022–23 drought); Ames, Iowa (corn–soy).
- **Alternatives:** California Central Valley (water story, but OpenET-heavy); Kenya as the main demo (less US partner data). Rejected because Nevada aligns with the challenge's own framing and with the USDA resources it lists.

## ADR-002 Challenge emphasis: rotations + weekly decisions (15:50)
- The official 2026 challenge text centres on **crop-rotation strategies** that improve soil health and resilience, and suggests comparing at least three of them, including the existing rotation. The build prompt centres on weekly water/pest/disease decisions. FieldShift does both, in two views of one engine: **"This week"** (action cards) and **"Field Shift"** (rotation explorer), plus What-if and Climate. Both are driven by the same season model and the same NASA data.

## ADR-003 Stack
- **Backend:** Python 3.13 + FastAPI + numpy/scipy, with no pandas, to keep the image small. **Client:** Expo (React Native + expo-router + TypeScript) for web, iOS and Android from one codebase. **Storage:** gzip JSON response cache on disk, with a committed demo cache. **Deploy:** Docker / docker-compose.
- Alternatives: Django; Flutter; PostGIS. Rejected because point-based time series at hackathon scale need no database. The scientific stack lives in Python, and Expo gives three platforms from one codebase.

## ADR-004 Data access without Earthdata credentials (16:00)
- No `EARTHDATA_TOKEN` was provided. NASA layers are accessed through **no-auth** services:
  - NASA POWER API (weather/radiation backbone).
  - ORNL DAAC Global Subsets REST API for MODIS MOD13Q1 NDVI, MOD16A2GF ET, MOD11A2 LST and SMAP SPL3SMP_E.
  - SRTM 30 m via OpenTopoData.
- Partner/open data:
  - Open-Meteo forecast and ERA5-Land archive (ECMWF/Copernicus; ERA5 is listed by the challenge).
  - SoilGrids (ISRIC).
  - US Drought Monitor (validation only).
- **Gap:** GPM IMERG, GRACE-FO and ECOSTRESS full products need Earthdata Login (ECOSTRESS subsets via ORNL are site-limited). Rain comes from NASA POWER `PRECTOTCORR` ("MERRA-2 bias corrected total precipitation", per the POWER parameter metadata); ET is cross-checked with MODIS MOD16. With an Earthdata token, IMERG would be the first upgrade (ROADMAP.md). Documented in DATA.md and LIMITATIONS.md.

## ADR-005 Season model: own FAO-56/FAO-33 implementation instead of AquaCrop-OSPy/PCSE (16:20)
- **Decision:** a transparent daily model:
  - FAO-56 single-Kc root-zone water balance.
  - Thermal-time phenology calibrated per location.
  - FAO-33 Ky yield response, plus heat and frost penalties.
- **Alternatives:** AquaCrop-OSPy (heavier, slower, numba compile; the parameter sets for teff and cover crops don't exist anyway); PCSE/WOFOST (needs detailed crop/soil files and is mostly for European crops).
- **Reason:** speed. One season runs in about 1 ms, so the rotation explorer can simulate 10 strategies × 4 slots × 15 years interactively. Every equation can also be explained in the "Why?" view. An AquaCrop-style WP*·ΣTr/ET₀ biomass diagnostic is reported alongside for comparison (EXPERIMENTS.md).

## ADR-006 Data processing on the Linux server (16:25)
- Per the user's instruction, heavy data jobs (demo-cache precompute, validation) run on `vps-home-node-1` (24 cores, 93 GB RAM, RTX 5070 Ti) in `tmux`.
- Access: the Mac reaches it over Tailscale with a dedicated key. The key was installed via SALE's WSL (see DEV_ENVIRONMENT.md).

## ADR-007 Git source of truth = Gitea on the VPS (16:30)
- The user asked to use the self-hosted Gitea, at `http://vps-home-node-1:3001/lino/fieldshift` (private).
- The Mac and the VPS both clone from it over SSH (port 2222). A GitHub mirror can be added for submission (SUBMISSION.md lists that as a human step).

## ADR-008 Offline/demo cache (16:40)
- The HTTP layer caches every response as gzip JSON, keyed by URL and parameters.
- `scripts/build_demo_cache.py` copies the cache for the demo presets into `backend/demo_cache`, which is committed.
- The offline mode (`FIELDSHIFT_OFFLINE=1`) falls back to a fuzzy match on the same endpoint and location with any date range. A pre-cached demo therefore keeps working on later days, and the UI labels it "offline".

## ADR-009 Irrigation history assumption (16:45)
- The model cannot see past irrigation on a 1–10 ha field: SMAP's 9 km pixel is dominated by surrounding desert.
- Default assumption: the farmer irrigated when the model said so. The user can enter the last irrigation date and amount, which raises the stated confidence.
- The assumption is shown in the card's caveats.

## ADR-010 Translations
- Server-generated card titles and details are translated in `config/messages.yaml` (en/es/fr/sw/hi/de). UI strings live in the client's i18n files.
- The step-by-step "Why?" reasoning is English-only in v1 (numbers are language-neutral). Listed in LIMITATIONS.md.

## ADR-011 "SI" terminology
- The 2026 Space Apps rules use "Super Intelligence (SI)" in place of "AI". Submission texts use "SI", with "AI" in parentheses on first use for clarity.
