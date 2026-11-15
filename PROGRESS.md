# PROGRESS

## FINAL SUMMARY (v1.0.0, 2026-11-15 ~00:30 CET; deadline Sun 2026-11-15 23:59)
**What was built:** FieldShift, an app on web, iOS and Android, with a FastAPI backend, that turns NASA Earth observations into:
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
- `SUBMISSION.md`: texts to paste.
- Git source of truth: Gitea `http://vps-home-node-1:3001/lino/fieldshift`.

**How to run:**
- `docker compose up --build` → http://localhost:8080 (API docs at `/docs`).
- `FIELDSHIFT_OFFLINE=1 docker compose up --build` for the fully offline demo.
- Mobile: `media/BUILDS.md`.

**What the human must still do** (see SUBMISSION.md checklist):
1. Push the repo to a public host (e.g. GitHub mirror) and paste the link.
2. Upload `media/fieldshift-demo-30s.mp4` (YouTube unlisted or Drive) and paste the link. Build the showcase page with `python3 scripts/build_site.py --repo <public URL>` and publish `site/dist`; this also puts the URL into the deck.
3. Check team registration, tick both boxes, and submit before Sun 23:59 local time.
4. Optional: public hosting (owner chose private, ADR-014).
5. Optional: rotate or revoke the Gitea tokens created for this build (`fieldshift-mac-*`, `fieldshift-sale-readonly-*`) and the Earthdata password stored on the VPS (`~/.config/fieldshift/earthdata`).

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
