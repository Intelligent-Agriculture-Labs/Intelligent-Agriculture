# PROGRESS

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
