# PROGRESS

## Repository publishing audit (2026-11-15)
Scanned all 1,654 tracked files and 3,163 historical blobs for common credential signatures; none found. No broken relative Markdown links found. Fixed the two formatting failures reported by GitHub CI and replaced the showcase builder’s default repository placeholder with the published URL. Local backend lint, formatting and type checks pass; all 233 backend tests and 60 app tests pass. App lint, TypeScript and formatting checks pass.

## Submission cleanup (2026-11-15)
Removed `SUBMISSION.md` at the owner’s request after they entered the submission fields. Updated README and challenge evidence links to the published presentation and retained source assets.

## Live NASA Earthdata feeds (2026-11-15 afternoon, branch `earthdata-live-feeds`, ADR-027)
- **GES DISC unlocked** (EULA approved): IMERG **Late/Early** fill the ~2 months IMERG Final lacks (V13b: beats the old bridge at 8/12 gauges on daily r, 9/12 on KGE); **GRACE-DA** weekly groundwater percentile next to the GRACE trend (+ card for irrigated fields at ≤ 10th percentile).
- **SMAP L4 and ECOSTRESS** read directly (NSIDC cloud OPeNDAP, LP DAAC COGs) after the AppEEARS jobs sat queued > 24 h; live for any field with an Earthdata Login on the server, demo fields offline.
- **V3 done:** model root-zone water vs SMAP L4, median per-season r 0.92 Iowa, 0.66 Córdoba, 0.64 Machakos. **V6 done:** large unresolved model–ECOSTRESS gap at Fallon (6.2 vs 2.3 mm/day) → ECOSTRESS shown, never acted on.

## v1.1.0: worldwide accuracy release (2026-11-15, ~03:40 CET)
Six validated work streams, each adopted only if it beat the previous version on held-out data:
- **Rain-season onset and false-start advisor** (V9): India IMD normals MAE 3.6 days; Sahel season length MAE 12.5 days.
- **Global yield calibration** (V10): FAOSTAT, 41 countries, held-out RMSLE 0.84 → 0.50.
- **Global pest and disease models** (V11): rice blast, rusts, tropical late blight, coffee rust, Sigatoka, desert locust, ...
- **Heat stress (WBGT/THI), solar pump, NASA FIRMS fires** (V12).
- **GPM IMERG rain blend** (V13; beats POWER at 16/18 gauges) and **GRACE/GRACE-FO water storage** (V14; 11/11 aquifers).
- **Learned field-edge model** (V15): held-out IoU 0.24 → 0.52 on 20 countries.
- **Not adopted:** a worldwide AI drought model (EXP-11 / ADR-020); rules stay outside the U.S.
- **Also:** coffee and banana crops (54 in total); fewer false alarms (leaf diseases need emerged leaves; saturating tropical models capped at moderate).
- **Human step:** approve the NASA GES DISC licence on the Earthdata account to unlock IMERG Late and the weekly GRACE groundwater percentiles.

## FINAL SUMMARY (v1.0.0, 2026-11-15 ~00:30 CET; deadline Sun 2026-11-15 23:59)
**What was built:** IA, an app on web, iOS and Android, with a FastAPI backend, that turns NASA Earth observations into:
- weekly farm actions (irrigation amount and date, drought, disease, pests, frost/heat) with a "Why?" for every number;
- per-field maps: computed terrain layers (erosion, wetness, frost, slope, zones); Sentinel-2 analytics (NDVI history, phenology, cuttings, AI zones); satellite-model data fusion;
- a season planner;
- a crop-rotation explorer: current rotation + ≥ 3 alternatives simulated on 15 seasons at the field;
- What-if scenarios and climate trends;
- tap-to-detect field boundaries, multiple fields, and account-free phone ↔ PC sync;
- an AI drought classifier, trained on USDM and validated on held-out counties;
- six languages and offline mode;
- accounts (phone ↔ PC), a minimalist 5-tab design with a first-run guide and a plain-language glossary;
- a multi-year, science-based rotation plan per field (54 crops, 30 pathogens) with an optimiser and an impact card;
- weekly advice as SMS text (≤ 2 SMS in 6 languages).

**Presentation:**
- `media/fieldshift-demo-30s.mp4`: a code-rendered cinematic film with an original score (`video/`);
- `media/fieldshift-deck.pdf`: the 7-slide deck;
- `site/`: the showcase page (`scripts/build_site.py`);
- native iPhone 17 screenshots in `media/iphone-*.png`.

**Pending at release:** validation checks V3 (SMAP) and V6 (ECOSTRESS/MOD16). Their NASA AppEEARS requests were still queued when v1.0.0 was cut; see VALIDATION.md.

**Where everything is:**
- `backend/`: API, science, ML model, committed offline demo cache.
- `app/`: Expo client, plus native capture scripts in `app/scripts/`.
- `docs/`: all documentation (VALIDATION, EXPERIMENTS, SELF_REVIEW, …).
- `media/`: web/iOS/Android screenshots, flow videos, the 30 s demo video, BUILDS.md.
- Submission text has been entered on the competition website; `SUBMISSION.md` was removed at the owner’s request.
- Git source of truth: Gitea `http://vps-home-node-1:3001/lino/fieldshift`.

**How to run:**
- `docker compose up --build` → http://localhost:8080 (API docs at `/docs`).
- `FIELDSHIFT_OFFLINE=1 docker compose up --build` for the fully offline demo.
- Mobile: `media/BUILDS.md`.

**Final submission steps** (updated 2026-11-15):
- Public source: https://github.com/Intelligent-Agriculture-Labs/Intelligent-Agriculture
- Published showcase: https://intelligent-agriculture-labs.github.io/
- Final video: `media/ia-demo-30s.mp4`; published showcase copy at `/assets/ia-demo-30s.mp4`.
- Owner reports the competition website fields are filled. Submission status and any YouTube/Drive upload have not been independently verified.
- Confirm the submitted video link opens without signing in, team registration is complete, references and SI disclosure are included, both required boxes are ticked, and final submission is confirmed before 23:59 local time.
- Remaining device check: login, live-data banner and coloured zones on the owner’s physical iPhone.

**Known limitations:** `docs/LIMITATIONS.md`. In short:
- coarse weather grids;
- assumed irrigation history;
- IMERG blend only between 45° S and 45° N, and GRACE storage is regional (~300 km);
- terraced plots need manual outline edits;
- the Esri basemap is licensed for demo use only;
- the ML model is U.S.-only.


Deadline: **Sun 2026-11-15 23:59 CET**. Phase plan: thin slice ≤ ~Sat 23:00 · feature freeze Sun ~16:00 · packaging Sun ~21:00.

## Log
| Time (CET) | Phase | Done | Next |
|---|---|---|---|
| Sat 15:40 | Step 0 | Read challenge, judging guide, rules (docs/CHALLENGE.md). Probed data APIs: POWER, ORNL subsets (MODIS/SMAP), Open-Meteo, SRTM, SoilGrids OK; Earthdata token absent | Scaffold |
| Sat 16:25 | Slice | VPS access (Tailscale + key via SALE WSL), Gitea origin, backend science core + API, tests green (26), lint/mypy clean. Advice works end-to-end on real data for Fallon | Demo cache + validation on VPS; client app (parallel agent) |
| Sat 16:45 | Slice | Validation running on VPS: ET0 vs ERA5 r=0.97–0.98 daily (temperate), soil water vs ERA5-Land median r≈0.71 | Docker, docs, app integration |

| Sat 17:35 | Depth | Thin slice done well ahead of plan (web + API on real NASA data). Client app complete (web; iOS/Android builds in progress by parallel worker). Validation-driven fixes: late-frost yield collapse (EXP-04), SPEI-12 in drought status (EXP-03), alfalfa cutting interval (EXP-05). Replay mode, off-season planning card, pest ranges, climate-zone + Mediterranean rotation logic. Docker/CI written. Docs: CHALLENGE, PRODUCT, DATA, MODELS, ARCHITECTURE, API, DEPLOYMENT, LIMITATIONS, ROADMAP, EXPERIMENTS, USER_GUIDE, SUBMISSION, README | Docker verify, native builds + media, satellite cache, final validation, video, self-review |

| Sat 18:30–19:15 | Depth (user requests) | Terrain maps (RUSLE, TWI, frost hollows, zones) + season planner; farm sync (no account), multi-field, field editor on sub-metre imagery; tap-to-detect field boundaries (EXP-10); Sentinel-2 field analytics (phenology, harvest detection, AI k-means zones, satellite Kcb fusion); AI drought classifier trained on USDM (EXP-09, adopted); presets moved to real farm fields; ECOSTRESS + SMAP via AppEEARS (Earthdata login) | UI for detection + harvest markers (worker), recaptures, final validation, video |

## Must-do before packaging
- Recapture all web screenshots on real data (first capture showed MOCK banner while /api/rotations was 500).
- Re-run full validation on final code; refresh numbers in VALIDATION.md / README / SUBMISSION.
- Commit backend/demo_cache from the VPS after enrichment jobs finish; verify FIELDSHIFT_OFFLINE=1 demo.

## Known issues
- ORNL DAAC subset API intermittently returns 502/503 → satellite layers come from the pre-built cache; live requests degrade gracefully (cards still work on POWER + forecast).
- SoilGrids REST times out intermittently → default loam (labelled) when unavailable.
