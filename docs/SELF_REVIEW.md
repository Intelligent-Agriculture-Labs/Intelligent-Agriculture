# Self-review: a strict Space Apps judge's scorecard

Scored against the official criteria (1–5 each), written as a judge who has read the repository, watched the 30 s video and run `docker compose up`. Each weak point lists what was done about it before submission.

| Criterion | Score | Evidence | Weakest point → action taken |
|---|---|---|---|
| **Impact** | 4.5 | Serves irrigated family farms (Nevada) and rain-fed smallholders (Kenya, Swahili, offline, payloads ~20 KB, **weekly advice in ≤ 2 SMS** in 6 languages). Weekly decisions, season plan and multi-year per-field rotation plan cover the whole decision cycle. The **impact card** quantifies each improved plan per field (water, N fertiliser, CO₂e, topsoil, income) and states trade-offs. Global by design | No real farmer validation yet; impact numbers are model estimates → said so on the card, the site and the deck; ROADMAP names extension partners and on-farm trials. Not fixable before the deadline |
| **Creativity** | 4.5 | Tap-to-detect field boundaries; satellite-detected cuttings vs. modelled ones; satellite Kcb fused into the water balance; a biologically based rotation checker (30 pathogens with survival times and regional ranges, legume N, cover crops) with a beam-search optimiser simulated on the field's own NASA weather; replay mode; SMS-length advice | Individual methods are known (FAO-56, RUSLE, k-means). The novelty is the integration and "one tap to evidence". Shown in the video |
| **Validity** | 4.5 | Published methods with equations (MODELS.md, ROTATION_SCIENCE.md with sources per rule); 55 backend + 58 client unit tests incl. FAO-56 worked examples and GSM 03.38 SMS sizing; 20 Playwright E2E (first run, accounts, planner, share) plus native capture tours; independent validation vs. ERA5, ERA5-Land, SMAP, ECOSTRESS, MOD16, USDM and documented drought years; the ML drought model was adopted only after it beat the rules on held-out counties | Weak results exist (Kenya soil water; Nevada USDM; late blight 3rd of 11) → reported in VALIDATION.md and LIMITATIONS.md. Field detection fails on terraced plots → the outline is always editable |
| **Relevance** | 5 | Directly answers the challenge: ≥ 3 rotation strategies incl. the existing one, with why/evidence/benefits/gaps/local-review risks; per-field multi-year plans; bare-field periods; vulnerable seasons; erosion risk and hotspots, wetness and frost maps; scenarios; farmer priorities; plain-language glossary. NASA data drive every number: POWER, SMAP, MODIS, ECOSTRESS, SRTM, GIBS; partner data: Sentinel-2, ERA5 | GPM IMERG and GRACE-FO are not integrated → stated in DATA.md and ROADMAP |
| **Presentation** | 4.5 | Minimalist 5-tab app with a first-run guide; 30 s video re-cut to the official template (team → challenge → title → how it works → vision) from real captures with English captions; 7-slide PDF deck; static showcase page (no login) generated from real screenshots and computed numbers; one-command run; offline demo | No public live URL (owner's decision, ADR-014) → video, deck, showcase page, `docker compose up`, `FIELDSHIFT_OFFLINE=1` |

**Overall: 4.6 / 5.**

## Fixes made during the self-review pass
1. Demo presets were in town centres. Moved to real farm fields with outlines detected or traced on sub-metre imagery.
2. Sentinel-2 NDVI saturated at 1.0 (Earth Search offset double-applied). Fixed and re-run (EXP-11 in the commit history).
3. Water-allocation coverage note was always "100 %" (planner compared against allocation-limited use). Now compares with the full-irrigation need.
4. Mock-data screenshots from an early capture were all recaptured on real data. The capture scripts refuse to run when the MOCK banner shows.
5. Machakos and Córdoba pins were in towns, which gave urban terrain statistics. Fixed by (1).
6. Weekly SMS text was miscounted (ASCII-only test, no concatenation headers) and used up to 4 parts. Now uses GSM 03.38 part sizes, GSM-7 normalisation and a 2-part budget; verified on all demo fields in 6 languages.
7. Machakos terrain zones showed one solid "erosion hotspot" block (the whole field is above 5 t/ha/yr). Now erosion risk vs. hotspot (≥ 10 t/ha/yr or the worst quarter), so the map shows where to act first.
8. Showcase impact figures were first drafted by hand. Replaced by numbers generated from the planner API (`scripts/site_impact.py`).

## Known residual risks
- **Public data services.** ORNL subsets, SoilGrids and the AppEEARS queue can be slow or down. Mitigated by the cache, the fallback chain and the committed demo dataset.
- **Esri basemap licence** for production. ADR-015; NAIP and Sentinel-2 alternatives are wired in.
- **SMAP for arbitrary new fields** needs an asynchronous AppEEARS task. The demo fields are pre-extracted.
