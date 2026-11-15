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

## ADR-021 Rain-season onset, false-start and sowing advisor (2026-11-15)
- **Context:** rain-fed farmers in the tropics lose seed, labour and weeks of season to false starts and late or short rains. FieldShift had no notion of a rainy season, and its sowing scan simulated calendar dates only.
- **Decision:**
  - **Published agroclimatic criteria, not a fitted model.**
    - Onset: Sivakumar (1988) / Stern et al. (1981), ≥ 20 mm in 3 days with no dry spell > 7 days in the next 30.
    - Cessation: a 100 mm water balance with ET₀ (Stern; FAO).
    - Seasons: Liebmann et al. (2012) anomalous accumulation, with the Dunning et al. (2016) harmonic test for bimodal regimes.
    - All thresholds are in `config/onset.yaml`, and the production defaults were fixed before validation.
  - **False-start risk is empirical and conditional:** the share of the site's historical apparent onsets, near the same date, that were followed by a damaging dry spell, given the days already checked by observations and the 16-day forecast.
  - **Sowing windows use FAO-56 stage lengths.** The crop must finish grain fill before the water-balance end in 8 of 10 seasons. If it can't, the card advises an early variety (≤ N days) or a shorter crop.
  - **Gating:** only for rain-fed fields with |lat| ≤ 35°, at least one rainy season and ≥ 60 dry days (P < ½ ET₀). Elsewhere there is no card, and the API answers `applicable: false` with the reason.
  - **Self-contained:** new modules `science/onset.py` and `engine/rain_season.py`; one registration line in `service.py`; an `onset_ok` filter in the planner scan; a new endpoint `GET /api/rain-season`. Contract fields are optional, so existing clients keep working.
- **Validation (V9):** 31 sites on 3 continents.
  - IMD 2020 normal onsets of 9 Indian cities: MAE 3.6 days.
  - Machakos OND onset: +2 days vs. Omoyo et al. (2015).
  - Darwin: +1 day vs. BoM.
  - Season length at 17 Sahel stations vs. Sivakumar: MAE 12.5 days, r = 0.96 (after requiring a confirmed end: no onset-sized refill within 21 days).
  - Weak spots, reported as they are:
    - In Kerala the agronomic onset falls ~5 weeks before IMD's monsoon onset (pre-monsoon showers already satisfy the criterion).
    - Niamey is +15 days, against a 1904–1984 reference.
    - Machakos MAM is −20 days (−9 with the study's own thresholds).
- **Rejected:**
  - Location-tuned thresholds: they would overfit 40 years of one grid cell.
  - Liebmann per-year onset as the advice trigger: it needs the whole season's rain, so it cannot be computed in real time.
  - The IMD circulation criteria: they need winds and OLR, which do not exist for a single point.
- **Consequences:**
  - The card says "agronomic start of the rains" and asks for a farmer's own rain gauge as the best check.
  - Cessation is bounded below by "3 weeks before the climatological end". This creates a small pile-up at that date in dry years, which shows in the p10/p20 of season length.

## ADR-022 Global yield calibration against FAOSTAT (2026-11-15)
- **Context:**
  - The season model's yield level came from `typical_yield_t_ha`: well-managed, mostly U.S./European yields. It had been checked only at the demo sites.
  - A Kenyan smallholder was shown 6.4 t/ha of maize at Machakos, where the national FAOSTAT mean is 1.6 t/ha.
- **Decision:**
  - Benchmark the model against FAOSTAT national yields worldwide (VALIDATION V9) and calibrate the level with a small set of documented multiplicative factors:
    - Y = Y_model × f_crop × f_region^s_crop
    - f_crop: potential-yield factor per crop (15), fitted where crops.yaml typical yields come from (Northern America, Western and Southern Europe), so f_region = 1 there;
    - f_region: yield-gap factor per UN M49 macro region (8);
    - s_crop: yield-gap sensitivity per crop (15), ridge-shrunk towards 1.
  - Factors are generated by `scripts/yield_benchmark.py evaluate --write-config` into `config/yield_calibration.yaml` with sources and country counts. They are never hand-edited.
  - The region comes from a committed 0.5° grid (`config/region_grid_30mn.npz`, 5 kB) derived from MIRCA2000 country units and UN M49 sub-regions, so it works offline.
  - Annual crops without FAOSTAT series get the regional factor with s = 1, so rotation comparisons in one place stay consistent. Perennials, forages and cover crops are not calibrated: Fallon alfalfa is unchanged.
  - Antecedent soil water (180-day fallow balance before sowing) becomes the default (EXP-12).
- **Alternatives:**
  - Climate-zone factors: worse on held-out countries once the region is known.
  - Per-country factors: not transferable to new countries, and they overfit.
  - A free crop×region table: ~140 factors for 0.013 RMSLE.
  - Unanchored structures: about 0.01 better RMSLE on average, but U.S./Spanish maize at about 0.7 of observed.
- **Consequences:**
  - The API shape is unchanged. Yields, margins and rotation rankings now reflect typical local management. Ames maize median 10.9 → 10.5 t/ha, Córdoba wheat 2.3 → 1.8, Machakos maize 6.4 → 1.1. Fallon is unchanged.
  - The feasibility screen ("below a third of normal") compares with the calibrated level, so low-input regions do not mark every crop infeasible.
  - Calibrated yields describe the *typical* farm in the region. A farmer with better management will exceed them; LIMITATIONS says so.
  - Re-running the benchmark (~20 min on the data box with a warm POWER cache) regenerates the factors and the V9 tables.

## ADR-023 Global pest & disease risk models (2026-11-15)
- **Context:** pest and disease advice covered mainly U.S./European examples (Hutton late blight, stripe rust, North American degree-day insects). The goal was scientifically sound advice for the world's major crops and farming regions.
- **Decision:** a separate, modular layer (`science/leafwet.py`, `science/globalrisk.py`, `engine/risk_cards.py`, texts in `config/pest_disease.yaml`). `service.py` has a one-line hook, so the change stays out of the files other work streams edit.
  - **One generic infection equation** for the fungal leaf diseases: the Magarey, Sutton & Thayer (2005) temperature–wetness model, W(T) = Wmin / f(T). Each pathogen gets its own Tmin/Topt/Tmax/Wmin/Wmax from the cited literature. The alternative, a separate ad-hoc rule per disease, is harder to audit and to validate.
  - **One shared leaf-wetness estimator** (RH ≥ 90 % or dew-point depression with hysteresis, with rain hours wet), so every model uses the same, cited wetness definition.
  - **Late blight:** the Hutton rule is UK-derived and needs Tmin ≥ 10 °C. Between the tropics it is replaced by Wallin severity values (BLITECAST/SimCast), which were field-tested in the Toluca highlands. Validation V11 shows Hutton finds 0 favourable days in the Ecuador highlands, where blight pressure is among the world's highest.
  - **Insects:** desert locust breeding is an *awareness* card that points to FAO Locust Watch and the national locust unit. FieldShift never gives control advice for locusts. Cassava whitefly is a qualitative warm-and-dry rule.
  - **No product or brand advice:** actions are scouting and cultural control, with treatment decisions referred to local thresholds and extension services. A unit test checks the texts.
- **Gating:** a card needs host crop, geographic range (continent, tropics or the FAO recession area), crop stage window and score threshold. Out-of-range or out-of-season fields never see the card.
- **Not done:** coffee and banana are not FieldShift crops yet. Adding them needs perennial crop-model parameters, which belong to the yield work stream. Their models are implemented, validated and ready, but no card appears until those crops exist.
- **Consequences:** validation results are reported per model in VALIDATION.md V11, including misses.
