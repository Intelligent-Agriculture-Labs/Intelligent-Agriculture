# Decisions (ADRs)

Format: decision · alternatives · reason. Newest at the bottom. Times are CET (Europe/Berlin).

## ADR-001 Project scope and demo regions (2026-11-14 15:45)
- **Name:** IA · Intelligent Agriculture.
- **Demo region:** Lahontan Valley (Fallon), Nevada, with irrigated alfalfa. The challenge's hero photo shows a Nevada alfalfa farmer. The region has severe, well-documented drought and water-delivery cuts and good NASA data coverage, and alfalfa is the classic "rotation question" crop. Three secondary presets show global reach: Machakos, Kenya (rain-fed smallholder maize); Córdoba, Spain (rain-fed wheat/sunflower after the 2022–23 drought); Ames, Iowa (corn–soy).
- **Alternatives:** California Central Valley (water story, but OpenET-heavy); Kenya as the main demo (less US partner data). Rejected because Nevada aligns with the challenge's own framing and with the USDA resources it lists.

## ADR-002 Challenge emphasis: rotations + weekly decisions (15:50)
- The official 2026 challenge text centres on **crop-rotation strategies** that improve soil health and resilience, and suggests comparing at least three of them, including the existing rotation. IA combines these with weekly water, pest and disease decisions, in two views of one engine: **"This week"** (action cards) and **"Field Shift"** (rotation explorer), plus What-if and Climate. Both are driven by the same season model and the same NASA data.

## ADR-003 Stack
- **Backend:** Python 3.13 + FastAPI + numpy/scipy, with no pandas, to keep the image small. **Client:** Expo (React Native + expo-router + TypeScript) for web, iOS and Android from one codebase. **Storage:** gzip JSON response cache on disk, with a committed demo cache. **Deploy:** Docker / docker-compose.
- Alternatives: Django; Flutter; PostGIS. Rejected because point-based time series at hackathon scale need no database. The scientific stack lives in Python, and Expo gives three platforms from one codebase.

## ADR-004 Data access without Earthdata credentials (16:00)
- The initial integration accesses NASA layers through **no-auth** services:
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

## ADR-006 Offline data processing
- Heavy dataset-generation and validation jobs run separately from the request-serving API. Only compact derived assets and the demo cache are committed.

## ADR-007 Public source repository
- Source code and documentation are published at https://github.com/Intelligent-Agriculture-Labs/Intelligent-Agriculture.

## ADR-008 Offline/demo cache (16:40)
- The HTTP layer caches every response as gzip JSON, keyed by URL and parameters.
- `scripts/build_demo_cache.py` copies the cache for the demo presets into `backend/demo_cache`, which is committed.
- The offline mode (`FIELDSHIFT_OFFLINE=1`) falls back to a fuzzy match on the same endpoint and location with any date range. A pre-cached demo therefore keeps working on later days, and the UI labels it "offline".
- Update (2026-11-15): `scripts/verify_offline_demo.py` checks the committed demo with the network blocked (all endpoints the app calls × 4 presets × 6 languages, `--today` for later days); `build_demo_cache.py` merges into the demo index instead of replacing it; offline, the satellite view falls back to the newest earlier week's analysis of the same field. Rebuild steps: docs/DATA.md#pre-cached-demo-dataset.

## ADR-009 Irrigation history assumption (16:45)
- The model cannot see past irrigation on a 1–10 ha field: SMAP's 9 km pixel is dominated by surrounding desert.
- Default assumption: the farmer irrigated when the model said so. The user can enter the last irrigation date and amount, which raises the stated confidence.
- The assumption is shown in the card's caveats.

## ADR-010 Translations
- Server-generated card titles and details are translated in `config/messages.yaml` (en/es/fr/sw/hi/de). UI strings live in the client's i18n files.
- The step-by-step "Why?" reasoning was English-only in v1; since v1.2 every farmer-facing backend text comes from the
  message catalogs in `backend/fieldshift/config/messages/*.yaml` in all six languages (scientific citations stay as
  published). `scripts/check_i18n.py` and `backend/tests/test_i18n.py` fail on any missing key or hard-coded English.

## ADR-011 "SI" terminology
- The 2026 Space Apps rules use "Super Intelligence (SI)" in place of "AI". Submission texts use "SI", with "AI" in parentheses on first use for clarity.

## ADR-012 Earthdata Login for SMAP via AppEEARS (17:25)
- ORNL's no-auth SMAP subsets returned "no data" for every demo site. AppEEARS requires Earthdata Login; credentials are configured outside version control.
- `scripts/appeears_smap.py` extracts SMAP L3E surface and L4 surface/root-zone/percentile series for the demo sites. They are committed as small gz files and used for the drought status (L4 root-zone percentile) and for validation (V3).
- Arbitrary new locations get no SMAP. AppEEARS is asynchronous, so live per-request extraction is on the roadmap.
- **Superseded by ADR-027 (2026-11-15):** the AppEEARS requests never finished; SMAP L4 and ECOSTRESS are now read directly (NSIDC OPeNDAP, LP DAAC COGs), live for any field when Earthdata Login is configured.

## ADR-013 Single container (17:20)
- Podman's DNS (aardvark) on the Linux test host refused queries, so the nginx → api proxy failed. FastAPI now serves the exported web app itself.
- One image, one port, the same behaviour on Docker and podman.

## ADR-015 Sub-metre imagery for drawing and detection (19:00)
- Field drawing and tap-to-detect use Esri World Imagery (global, sub-metre) by default, with USDA NAIP (public domain) as the U.S. option. 10 m Sentinel-2 is too coarse to see field edges.
- **Licence note:** Esri's basemap is used with attribution for this non-commercial hackathon demo. A production deployment needs an Esri/ArcGIS key or a licensed imagery source. Detection works on any RGB tile source (NAIP in the U.S.).

## ADR-016 AI components chosen (19:10)
- **Supervised:** a drought classifier trained on USDM labels. It is adopted only where it beat the rules on held-out counties (EXP-09).
- **Unsupervised:** k-means management zones on Sentinel-2 + terrain.
- **Computer vision:** field-boundary detection.
- **Data fusion:** satellite Kcb into the water balance.
- An LLM is deliberately **not** used to generate advice. Every number stays traceable to data and published methods.
- A foundation-model segmenter (SAM) for field boundaries is on the roadmap as an optional GPU service.

## ADR-017 Accounts (20:00)
- E-mail + password accounts with server-side sessions (no external identity provider: the deployment must run offline and self-hosted).
- **Alternatives:** OAuth (needs public callback URLs and provider apps); magic links (need a mail server).
- **Limitation:** no e-mail verification or password-reset mail. Documented in LIMITATIONS.md; a reset needs the owner/admin.

## ADR-018 Rotation planning grounded in a cited knowledge base (20:00)
- Rotation biology comes from a YAML knowledge base compiled from extension services and peer-reviewed reviews (`docs/ROTATION_SCIENCE.md`), not from hand-tuned code. The checker explains every issue in plain language with its source.
- The optimiser is constrained to the farm type, so it does not tell an arable farmer to become a vegetable grower.

## ADR-014 Self-hosted application and public presentation
- The application runs locally or on a self-hosted server using Docker Compose.
- The public showcase, video and slides demonstrate the project without requiring an application account.

## ADR-019 Public presentation and impact reporting
- **Public final-project link** (required; no login). The public GitHub repository and static showcase site (`site/`, GitHub Pages).
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
  - Data stays on the processing host. Only scripts, metrics and the model are committed.
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
- **Context:** rain-fed farmers in the tropics lose seed, labour and weeks of season to false starts and late or short rains. IA had no notion of a rainy season, and its sowing scan simulated calendar dates only.
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
  - Benchmark the model against FAOSTAT national yields worldwide (VALIDATION V12) and calibrate the level with a small set of documented multiplicative factors:
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
  - Re-running the benchmark (~20 min on the processing host with a warm POWER cache) regenerates the factors and the V10 tables.

## ADR-023 Global pest & disease risk models (2026-11-15)
- **Context:** pest and disease advice covered mainly U.S./European examples (Hutton late blight, stripe rust, North American degree-day insects). The goal was scientifically sound advice for the world's major crops and farming regions.
- **Decision:** a separate, modular layer (`science/leafwet.py`, `science/globalrisk.py`, `engine/risk_cards.py`, texts in `config/pest_disease.yaml`). `service.py` has a one-line hook, to keep the risk models independent of the core service.
  - **One generic infection equation** for the fungal leaf diseases: the Magarey, Sutton & Thayer (2005) temperature–wetness model, W(T) = Wmin / f(T). Each pathogen gets its own Tmin/Topt/Tmax/Wmin/Wmax from the cited literature. The alternative, a separate ad-hoc rule per disease, is harder to audit and to validate.
  - **One shared leaf-wetness estimator** (RH ≥ 90 % or dew-point depression with hysteresis, with rain hours wet), so every model uses the same, cited wetness definition.
  - **Late blight:** the Hutton rule is UK-derived and needs Tmin ≥ 10 °C. Between the tropics it is replaced by Wallin severity values (BLITECAST/SimCast), which were field-tested in the Toluca highlands. Validation V11 shows Hutton finds 0 favourable days in the Ecuador highlands, where blight pressure is among the world's highest.
  - **Insects:** desert locust breeding is an *awareness* card that points to FAO Locust Watch and the national locust unit. IA never gives control advice for locusts. Cassava whitefly is a qualitative warm-and-dry rule.
  - **No product or brand advice:** actions are scouting and cultural control, with treatment decisions referred to local thresholds and extension services. A unit test checks the texts.
- **Gating:** a card needs host crop, geographic range (continent, tropics or the FAO recession area), crop stage window and score threshold. Out-of-range or out-of-season fields never see the card.
- **Not done:** coffee and banana are not IA crops yet. Adding them needs perennial crop-model parameters, which belong to the yield work stream. Their models are implemented, validated and ready, but no card appears until those crops exist.
- **Consequences:** validation results are reported per model in VALIDATION.md V11, including misses.

## ADR-024 Heat stress, solar pump and FIRMS fire advice as modular cards (2026-11-15)
- **Context.** The challenge asks for NASA-data advice that helps farmers anywhere. Three gaps were missing:
  - heat risk to the *people and animals* on the farm (the existing `heat` card covers crops only);
  - an energy option for irrigation;
  - fire and residue-burning advice for regions such as South Asia.
- **Decisions.**
  - **WBGT, not heat index.** ISO 7243 and NIOSH define work–rest limits in WBGT, and WBGT includes sun and wind, which matter outdoors. We implemented the physically based Liljegren et al. (2008) model rather than a regression (e.g. Bernard or the simplified "ABM" WBGT), because it uses exactly the variables we have (T, RH, wind, irradiance) and is the reference method. It is checked against ECMWF thermofeel to < 0.02 °C (VALIDATION V12).
  - **NIOSH time-weighted limits.** Work–rest fractions come from the NIOSH REL equation with a time-weighted metabolic rate, instead of a hard-coded ACGIH table. This keeps the advice continuous and citable.
  - **Livestock THI with cited species thresholds**: St-Pierre 2003 classes (Hahn 2009) and Marai 2007 for sheep and goats. Mild "alert" stress does not raise a card on its own. In live runs it fired on ordinary warm days in the tropics.
  - **Hourly inputs degrade gracefully**: forecast (Open-Meteo) → NASA POWER hourly in replays → context T/RH + NASA POWER climatology. The existing forecast request was *not* changed, so the committed demo-cache keys stay valid. Extra variables come from a separate request that may fail.
  - **Solar pump in its own module and endpoint** (`/api/solar-pump`), plus one low-priority `planning` card for irrigated fields. Sizing uses the design-month method (FAO/GIZ SPIS). Costs live in `config/solar_pump.yaml` because they vary by country. The diesel comparison excludes pump-set purchase, which is conservative for solar.
  - **FIRMS without a mandatory key.** The area API needs a free MAP_KEY. Without one, the public keyless 24 h global VIIRS files are used, then recorded demo detections (Punjab/Haryana, 7–14 Nov 2026), then nothing. The key never enters the cache key, logs or responses. `FIELDSHIFT_FIRMS=off|demo|auto` controls the mode (DATA.md).
  - **Residue-burning regions** are a small cited table of boxes, crops and months, not a model. The card is advice with quantified nutrient and carbon losses (Dobermann & Fairhurst 2002; Powlson et al. 2008), and Happy Seeder as the recommended alternative (Shyamsundar et al. 2019).
  - **Minimal coupling.** `service.py` gains three `cards.extend(...)` lines, one background FIRMS future and `firms` in the source list. `FieldContext` gains one field (`power`, the raw POWER daily record) so climatologies need no extra request.
- **Consequences.**
  - The heat card can show for any crop and season. It is the most broadly useful of the three for smallholders in hot climates.
  - In calm deserts the offline fallback under-estimates WBGT (−1.5 °C at Fallon in July). That case is flagged with lower confidence.
  - The keyless FIRMS mode downloads ~14 MB per 3 h per server. Deployments with traffic should set a MAP_KEY.

## ADR-025 NASA GPM IMERG rain blend and GRACE/GRACE-FO water-storage trend (2026-11-15)
- **Context:** IMERG and GRACE-FO were the first Earthdata upgrades on the roadmap. POWER's MERRA-2 rain is weakest in the tropics; irrigated farms had no signal about long-term water supply. Earthdata Login is configured on the processing server.
- **IMERG route:** GES DISC OPeNDAP, the cloud OPeNDAP/data endpoints and Giovanni all need the "NASA GESDISC DATA ARCHIVE" EULA approved on the Earthdata account (approved for the live integration in ADR-027), and the data-rods service timed out. NASA POWER serves `IMERG_PRECTOT` (IMERG Final, 0.1°, from 1998) anonymously through the same point API — chosen: worldwide, no key, same cache and offline chain. POWER returns IMERG only for `time-standard=UTC`.
- **IMERG decision (V13):** serve 0.5·POWER + 0.5·IMERG daily between 45° S and 45° N; POWER × (0.5 + 0.5·climatological ratio) on days without IMERG; POWER alone poleward. The 0.5 weight was declared before the run. The blend beat POWER at 16/18 gauges on daily r and monthly KGE, in both climate zones, so the adoption rule ("only where it helps") gives both zones but not the unvalidated high latitudes.
- **Train/serve consistency:** the AI drought classifier keeps POWER-only rain features (it was trained on them; feeding the blend moved Fallon from D0 to D2 with unchanged SPI/SPEI), and the climate-trend analysis since 1984 keeps POWER-only rain (homogeneous record). `FieldContext.rain_power` carries that series.
- **GRACE route:** JPL RL06.3 CRI mascons from PO.DAAC (Earthdata Login worked there), compacted by `scripts/grace_extract.py` into a committed 0.7 MB global asset (distinct land mascon series + 0.5° index + JPL scale factors). No runtime network, works offline everywhere.
- **GRACE decision (V14):** a harmonic + linear trend with AR(1)-adjusted significance, five classes with a 0.3 cm/yr floor. Shown in the drought status as context (not in the level: 2–3 month latency, ~300 km, not validated against drought labels); a planning card for irrigated fields where storage is falling; the rotation ranking weights water 1.5× (declining) or 1.25× (likely declining) there. Because wells at Fallon are flat while the region falls, the card says "regional water reserves", not "groundwater under your field".
- **Consequences:** new modules only (`science/rainblend.py`, `science/groundwater.py`, `data/grace.py`, `engine/water_supply.py`), a few hook lines in `context.py` and `service.py`, optional fields in the API contract (`drought.groundwater`, `drought.rain_source`, `rotations.groundwater_note`). Refreshing GRACE needs `scripts/grace_extract.py` on the processing host; IMERG refreshes itself through POWER.

## ADR-026 Learned field-edge model + candidate selector for tap-to-detect (2026-11-15)
- **Context:**
  - Tap-to-detect (ADR-015, EXP-10) had been tuned on four demo fields.
  - A global benchmark (467 FTW fields, 25 countries; VALIDATION V15) measured a mean IoU of only 0.24. The method leaked into neighbouring fields everywhere, and smallholder Africa and Asia were near zero.
- **Decision:**
  - Replace the default with v3. A tiny U-Net edge map (1 MB) feeds scale-adaptive flood-fill candidates, ranked by a 58 KB gradient-boosted IoU predictor plus a rim-contrast prior.
  - Both models are evaluated in numpy on CPU (no deep-learning runtime).
  - Adoption rule, fixed in advance: mean IoU must improve on held-out countries, without regression on the demo fields. Result: 0.24 → 0.52 on 20 held-out countries, every country better. Demo fields are equal or better on visual check (EXP-13).
- **Data and licences:**
  - Training labels: FTW polygons of four countries, AT (CC-BY-4.0), FR (Licence Ouverte), NL (CC0) and ES (CC-BY-4.0).
  - Training imagery: open national orthophotos of the same four countries (IGN, PNOA, PDOK, basemap.at; Licence Ouverte / CC-BY 4.0).
  - No Esri imagery is used for training. Countries with non-commercial or GPL labels are used for evaluation only, and no FTW polygons are redistributed.
- **Unchanged:** the API response shape (`polygon`, `area_ha`, `confidence`, `touches_border`, `method`, `imagery`, `pixel_m`, `params`, `note`) and the offline behaviour (tiles from cache or demo cache, else `DataUnavailable`).
  - `confidence` is now the predicted IoU, which fits the app's existing 0.4 / 0.7 risk bands.
  - `method` names the pipeline that ran.
- **Fallback:** if the model files are absent, the v2 classical pipeline runs automatically.
- **Alternatives:**
  - SAM-class promptable segmenters: hundreds of MB and GPU-bound (stays on the roadmap as an optional service).
  - ONNX Runtime or PyTorch on the server: new heavy dependency for a 0.5 M-parameter net.
  - Tuning the classical method only: DEV 0.25 → 0.33, far below the learned variant.
- **Consequences:**
  - Retraining is scripted (`scripts/fieldedge/`, about 1 h, mostly orthophoto download).
  - The models are versioned in `backend/fieldshift/models/`.
  - Smallholder plots and > 100 ha fields remain the weakest cases (LIMITATIONS).

## ADR-027 Live Earthdata layers: IMERG Late/Early, GRACE-DA, SMAP L4, ECOSTRESS (2026-11-15)
- **Context:**
  - The GES DISC EULA and the other Earthdata applications were approved on the project account (15 Nov).
  - The AppEEARS point requests for SMAP and ECOSTRESS/MOD16 (ADR-012) had been `processing`/`pending` for > 24 h, so V3 and V6 were still open, and SMAP/ECOSTRESS existed only as planned files for the demo fields.
  - IMERG Final reaches the app ~2–3 months late (POWER), so the most recent, decision-relevant rain used a climatological bridge.
- **Routes chosen (all point reads, no batch queue):**
  - GES DISC through the **Giovanni time-series API** (one request per variable and field, ~2.5 s): IMERG Late and Early daily rain, GRACE-DA weekly groundwater/root-zone/surface percentiles. Giovanni needs its own token from `/signin` via Earthdata Login; an EDL bearer token is rejected. Per-day OPeNDAP reads of IMERG would have cost ~60 requests per field.
  - **SMAP L4** (`SPL4SMGP.008`) through NSIDC **cloud OPeNDAP**: CMR finds the granules (no login), one `.ascii` request reads root zone, surface and percentile at the 9 km EASE-Grid 2.0 cell (computed analytically, `ease2_m09`). One 10:30 UTC analysis per day.
  - **ECOSTRESS** (`ECO_L3T_JET.002` `ETdaily`): CMR point search, then one pixel of each Cloud-Optimized GeoTIFF via an EDL bearer token → signed S3 URL → GDAL range read (rasterio was already a dependency).
  - **MOD16A2GF** for V6 through LP DAAC cloud OPeNDAP (ORNL subsets answered HTTP 503).
  - No new Python dependencies: DAP2 `.ascii` and Giovanni CSV are parsed in a few lines.
- **Credentials:** env `EARTHDATA_USER/PASS`, `~/.config/fieldshift/earthdata` (mode 600) or `~/.netrc`; `FIELDSHIFT_EARTHDATA=off` disables. Credentials and tokens are never logged, never part of a cache key, and never committed; the committed demo-cache entries hold URL + parameters + data only.
- **Fallbacks:** every layer goes through `http.cached_call` (disk cache → committed demo cache → fuzzy offline match → unavailable). `/api/advice` fetches them in parallel within a 15 s budget (`engine/live_layers.py`); anything missing is simply left out, and the app behaves as before without an Earthdata account.
- **Decisions on use, from the validations:**
  - **IMERG Late/Early** fill the days after the last IMERG Final day with the same 50/50 blend (V13b: better than the old climatological bridge at 8/12 gauges on daily r and 9/12 on monthly KGE). Final replaces Late automatically once POWER serves it.
  - **SMAP L4** root-zone percentile feeds `drought.sm_percentile` (where L4 has no percentile, the rank of today's value within the same ±30 days of the site record; no level changed at the four demo fields). `water.satellite.smap` compares it with the model; a low-risk `smap_check` card appears for **rain-fed** fields when they clearly disagree (SMAP ≤ 20th percentile while the model has ≥ 70 % water left, or ≥ 80th while ≤ 40 %). Irrigated fields get the comparison as context only (a 9 km cell does not see one field's irrigation). Basis: V3 (median per-season r 0.64–0.92).
  - **GRACE-DA** groundwater percentile is shown next to the mascon trend (`drought.grace_da`, context only, not part of the level). Irrigated fields at ≤ 10th percentile get a `groundwater_low` planning card. Not validated beyond what GSFC publishes for the product; the card says "check your well".
  - **ECOSTRESS** is shown, never acted on: V6 found the model and ECOSTRESS far apart at the Fallon alfalfa field (6.2 vs 2.3 mm/day, r ≈ 0), so a planned "crop uses less water than expected" card was not adopted.
- **Demo fields:** `data/smap_points` (2015 → today) and `data/et_points` hold the pre-extracted series; `scripts/cache_earthdata_demo.py` adds the live-layer responses for the four presets (live and replay dates) to `backend/demo_cache`, so the offline demo shows them.
- **Not done:** AppEEARS remains in `scripts/appeears_smap.py` for reference; the SMAP L3E product is not extracted (L4 replaces it); OpenET (API key) and flux-tower data that could settle V6 are not integrated.

## ADR-028 Country-specific prices, costs, currency, sowing dates and yield level (2026-11-15)
- **Context:** Calculations require country-specific inputs for the field location. An audit found single global/U.S. numbers in: crop prices and costs (`crops.yaml`, U.S. 2023–24, used by the rotation explorer, the rotation plan, candidate ranking and plan impact), the N price for legume credits (1.3 USD/kg), solar-pump capex (1,000 USD/kWp) and diesel (1.10 USD/L), the tropical "30 % input share" shortcut, rotation sowing dates (a northern-temperate calendar shifted by hemisphere), and the yield calibration (macro-region only). Irrigation efficiencies are per method (FAO), soil comes from SoilGrids at the field, and USDM/NASS data are used only for validation or the U.S.-only drought classifier, so those stay.
- **Decision:**
  - Offline country lookup from a 5′ Natural Earth admin-0 raster (111 KB).
  - Per-country table (`config/country_data.json`, generated by `scripts/build_country_data.py` from FAOSTAT PP/QCL, World Bank WDI and Pink Sheet, CLDR, Sacks 2010). Crop prices: FAOSTAT national producer prices; costs: reference budget × national yield level × World Bank price level; currency: World Bank official rate; diesel: WDI archive pump price + crude-cost change; PV capex: installation share scaled by price level; sowing: Sacks cell or country median where it replaces the generic temperate default (tropical onset and Mediterranean rules from the field's own rainfall are kept), with the observed season length for the thermal-time target; yield: a country factor on top of ADR-022.
  - Explicit fallback ladder (country → UN M49 sub-region median → world median → reference × farm-price index); `fallback: true` only when no country is found. Every response with money has an `economics` block (country, currency, exchange rate and year, per-crop price/cost scope, years and source, N price, yield factor) and `*_local` amounts next to the unchanged USD fields.
  - Internally everything stays in USD so scores and thresholds keep their calibration; display converts.
- **Alternatives:** live World Bank/FAOSTAT queries at run time (slow, flaky — the WB API returned 502 for most bulk requests during the build — and not offline); one regional price table (still not the field's country); asking the farmer for every price (kept as an override for diesel/capex, too much friction as the default).
- **Consequences:**
  - Margins, rankings, plan impact and solar costs changed for every demo field; presentation and `site/impact.json` numbers were recomputed (Kenya fertiliser N saved 105 → 50 kg/ha; Spain fewer bare days 71 → 136/yr; Nevada irrigation saved 15,485 → 9,263 m³/yr; Iowa topsoil kept 481 → 532 t), because country prices, costs, yield factors and observed sowing dates change which plan the optimiser picks.
  - The tropical revenue-share shortcut is no longer used (country costs replace it); `score_strategy(smallholder=…)` remains only for callers without a country.
  - Costs and the N price remain modelled/world values; this is stated in LIMITATIONS and in the API (`cost_scope`, `nitrogen.scope`).
