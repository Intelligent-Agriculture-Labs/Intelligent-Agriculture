# PROGRESS

Deadline: **Sun 2026-11-15 23:59 CET**. Phase plan: thin slice ≤ ~Sat 23:00 · feature freeze Sun ~16:00 · packaging Sun ~21:00.

## Log
| Time (CET) | Phase | Done | Next |
|---|---|---|---|
| Sat 15:40 | Step 0 | Read challenge, judging guide, rules (docs/CHALLENGE.md). Probed data APIs: POWER, ORNL subsets (MODIS/SMAP), Open-Meteo, SRTM, SoilGrids OK; Earthdata token absent | Scaffold |
| Sat 16:30 | Slice | VPS access (Tailscale + key via SALE WSL), Gitea origin, backend science core + API, tests green (26), lint/mypy clean. Advice works end-to-end on real data for Fallon | Demo cache + validation on VPS; client app (parallel agent) |
| Sat 17:00 | Slice | Validation running on VPS: ET0 vs ERA5 r=0.97–0.98 daily (temperate), soil water vs ERA5-Land median r≈0.71 | Docker, docs, app integration |

## Known issues
- ORNL DAAC subset API intermittently returns 502/503 → satellite layers come from the pre-built cache; live requests degrade gracefully (cards still work on POWER + forecast).
- SoilGrids REST times out intermittently → default loam (labelled) when unavailable.
