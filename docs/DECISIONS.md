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

## ADR-012 Earthdata Login for SMAP via AppEEARS (17:25)
- ORNL's no-auth SMAP subsets return "no data" for every demo site, so the user provided an Earthdata Login. It is stored only on the VPS (`~/.config/fieldshift/earthdata`, mode 600) and never committed.
- `scripts/appeears_smap.py` extracts SMAP L3E surface and L4 surface/root-zone/percentile series for the demo sites. They are committed as small gz files and used for the drought status (L4 root-zone percentile) and for validation (V3).
- Arbitrary new locations get no SMAP. AppEEARS is asynchronous, so live per-request extraction is on the roadmap.

## ADR-013 Single container (17:20)
- Podman's DNS (aardvark) on the Linux test host refused queries, so the nginx → api proxy failed. FastAPI now serves the exported web app itself.
- One image, one port, the same behaviour on Docker and podman.

## ADR-015 Sub-metre imagery for drawing and detection (19:00, user feedback "not high-res enough")
- Field drawing and tap-to-detect use Esri World Imagery (global, sub-metre) by default, with USDA NAIP (public domain) as the U.S. option. 10 m Sentinel-2 is too coarse to see field edges.
- **Licence note:** Esri's basemap is used with attribution for this non-commercial hackathon demo. A production deployment needs an Esri/ArcGIS key or a licensed imagery source. Detection works on any RGB tile source (NAIP in the U.S.).

## ADR-016 AI components chosen (19:10)
- **Supervised:** a drought classifier trained on USDM labels. It is adopted only where it beat the rules on held-out counties (EXP-09).
- **Unsupervised:** k-means management zones on Sentinel-2 + terrain.
- **Computer vision:** field-boundary detection.
- **Data fusion:** satellite Kcb into the water balance.
- An LLM is deliberately **not** used to generate advice. Every number stays traceable to data and published methods.
- A foundation-model segmenter (SAM) for field boundaries is on the roadmap as an optional GPU service.

## ADR-017 Accounts (20:00, user request "the account system needs to work")
- E-mail + password accounts with server-side sessions (no external identity provider: the deployment must run offline and self-hosted).
- **Alternatives:** OAuth (needs public callback URLs and provider apps); magic links (need a mail server).
- **Limitation:** no e-mail verification or password-reset mail. Documented in LIMITATIONS.md; a reset needs the owner/admin.

## ADR-018 Rotation planning grounded in a cited knowledge base (20:00, user request "biologically based, insanely science based")
- Rotation biology comes from a YAML knowledge base compiled from extension services and peer-reviewed reviews (`docs/ROTATION_SCIENCE.md`), not from hand-tuned code. The checker explains every issue in plain language with its source.
- The optimiser is constrained to the farm type, so it does not tell an arable farmer to become a vegetable grower.

## ADR-014 No public hosting (18:15, user decision)
- The user chose to keep the demo private: no tunnel or public URL.
- Judges get the 30 s video, the screenshots, and `docker compose up --build` (or the offline mode).
- SUBMISSION.md lists hosting as an optional human step.

## ADR-019 Award-readiness additions (20:50, after re-reading the Space Apps submission guide)
- **Public final-project link** (required; no login). The public GitHub repo (owner step) plus a static showcase site (`site/`, GitHub Pages-ready).
- **Video re-cut to the official 30 s template:** 0:00 team, 0:02 challenge and inspiration, 0:05 title and tagline, 0:10 how it works with NASA and partner data, 0:20–0:30 future vision.
- **Impact quantification in the rotation planner:** current vs. improved plan in water, fertiliser N, CO₂e (IPCC 2019 direct N₂O emission factor EF1 = 0.01 kg N₂O-N per kg N × 44/28 × GWP100 273 from AR6 = 4.29 kg CO₂e per kg N avoided; manufacturing emissions conservatively not counted), soil loss and margin.
- **Low-bandwidth plain-text advice** (SMS/WhatsApp) in six languages for farmers without smartphones or data.
- **7-slide PDF deck** as an alternative demo format.

## ADR-020 Global drought classifier: evaluated, not adopted (2026-11-15)
- **Context:** the AI drought classifier (EXP-09) is trained on USDM and served only in the contiguous U.S. The goal was a model that is accurate worldwide, proven by held-out validation.
- **Labels chosen:**
  - **EDO Combined Drought Indicator** for Europe: categorical, open netCDF, CC BY 4.0.
  - **GDO Soil Moisture Index Anomaly** as a global *weak* label: open, CC BY 4.0, and independent of NASA POWER rain.
  - **Rejected:**
    - BoM rainfall deficiency and SPEIbase: rainfall- or SPEI-based, so nearly circular with the model's own features. BoM's terms are also not an open licence.
    - GDO RDrI-Agri: includes exposure and vulnerability, not only hazard.
  - Data stays on the data box. Only scripts, metrics and the model are committed.
- **Validation design:**
  - U.S. county GroupKFold, leave-one-region-out and leave-one-climate-zone-out, against the current model and the rules on identical samples.
  - The adoption rule was declared in the script before the first run: at least as good in the U.S., better in held-out Europe and in the pooled weak regions.
  - One extra candidate (no class balancing) was added after seeing the first run. It is labelled as post hoc and checked second.
- **Decision:** keep the current U.S.-only model and the rule-based status elsewhere.
  - The class-balanced global model passed the U.S. and weak-region checks but failed Europe: within ±1 0.847 vs. 0.859, Spearman 0.488 vs. 0.493.
  - The unbalanced one failed all three.
  - Outside the U.S. the rules beat both the current and the global model on within ±1 in every held-out region.
- **Consequences:**
  - The serving code is now region-gated by model metadata (`model_regions`, `feature_set`, `served_key`), so a future model can be switched on per validated region without code changes.
  - The cache writer uses a per-process temporary file. Parallel training workers had raced on it.

## ADR-021 NASA GPM IMERG rain blend and GRACE/GRACE-FO water-storage trend (2026-11-15)
- **Context:** IMERG and GRACE-FO were the first Earthdata upgrades on the roadmap. POWER's MERRA-2 rain is weakest in the tropics; irrigated farms had no signal about long-term water supply. Earthdata Login exists only on the data box.
- **IMERG route:** GES DISC OPeNDAP, the cloud OPeNDAP/data endpoints and Giovanni all need the "NASA GESDISC DATA ARCHIVE" EULA approved on the Earthdata account (not done; accepting a licence is the account owner's decision), and the data-rods service timed out. NASA POWER serves `IMERG_PRECTOT` (IMERG Final, 0.1°, from 1998) anonymously through the same point API — chosen: worldwide, no key, same cache and offline chain. POWER returns IMERG only for `time-standard=UTC`.
- **IMERG decision (V-IMERG):** serve 0.5·POWER + 0.5·IMERG daily between 45° S and 45° N; POWER × (0.5 + 0.5·climatological ratio) on days without IMERG; POWER alone poleward. The 0.5 weight was declared before the run. The blend beat POWER at 16/18 gauges on daily r and monthly KGE, in both climate zones, so the adoption rule ("only where it helps") gives both zones but not the unvalidated high latitudes.
- **Train/serve consistency:** the AI drought classifier keeps POWER-only rain features (it was trained on them; feeding the blend moved Fallon from D0 to D2 with unchanged SPI/SPEI), and the climate-trend analysis since 1984 keeps POWER-only rain (homogeneous record). `FieldContext.rain_power` carries that series.
- **GRACE route:** JPL RL06.3 CRI mascons from PO.DAAC (Earthdata Login worked there), compacted by `scripts/grace_extract.py` into a committed 0.7 MB global asset (distinct land mascon series + 0.5° index + JPL scale factors). No runtime network, works offline everywhere.
- **GRACE decision (V-GRACE):** a harmonic + linear trend with AR(1)-adjusted significance, five classes with a 0.3 cm/yr floor. Shown in the drought status as context (not in the level: 2–3 month latency, ~300 km, not validated against drought labels); a planning card for irrigated fields where storage is falling; the rotation ranking weights water 1.5× (declining) or 1.25× (likely declining) there. Because wells at Fallon are flat while the region falls, the card says "regional water reserves", not "groundwater under your field".
- **Consequences:** new modules only (`science/rainblend.py`, `science/groundwater.py`, `data/grace.py`, `engine/water_supply.py`), a few hook lines in `context.py` and `service.py`, optional fields in the API contract (`drought.groundwater`, `drought.rain_source`, `rotations.groundwater_note`). Refreshing GRACE needs `scripts/grace_extract.py` on the data box; IMERG refreshes itself through POWER.
