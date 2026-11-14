# Self-review: a strict Space Apps judge's scorecard

Scored against the official criteria (1–5 each), written as a judge who has read the repository, watched the 30 s video and run `docker compose up`. Each weak point lists what was done about it before submission.

| Criterion | Score | Evidence | Weakest point → action taken |
|---|---|---|---|
| **Impact** | 4.5 | Serves irrigated family farms (Nevada) and rain-fed smallholders (Kenya, Swahili, offline, cheap-phone payloads ~20 KB). Weekly decisions + season plan + rotation strategy cover the whole decision cycle. Global by design (POWER, Sentinel-2, SRTM, Esri imagery) | No real farmer validation yet → USER_GUIDE written for non-experts; ROADMAP #9 names extension partners for co-design. Not fixable before the deadline |
| **Creativity** | 4.5 | Tap-to-detect field boundaries; satellite-detected cuttings compared with modelled ones; satellite Kcb fused into the water balance; rotation explorer that simulates each alternative on 15 seasons *at that field*; replay mode on real past weeks; account-free sync | Individual methods are known (FAO-56, RUSLE, k-means). The novelty is the integration and the farmer-facing "one tap to evidence". Shown in the video storyboard |
| **Validity** | 4.5 | Published methods with equations (MODELS.md); 46 backend + 39 client unit tests incl. FAO-56 worked examples; E2E on web (Playwright) and native capture tours; independent validation vs. ERA5, ERA5-Land, SMAP, ECOSTRESS, MOD16, USDM, documented drought years; ML model adopted only after it beat the rules on held-out counties; usability: ≤ 3 cards, 6 languages, offline | Weak results exist (Kenya soil water; Nevada USDM; late blight 3rd of 11) → reported in VALIDATION.md and LIMITATIONS.md instead of hidden. Field detection fails on terraced plots → outline is always editable |
| **Relevance** | 5 | Directly answers the challenge: ≥ 3 rotation strategies incl. the existing one, each with why/evidence/benefits/gaps/local-review risks; bare-field periods; vulnerable seasons; field-level erosion, wetness and frost maps; scenario sliders; farmer priorities. NASA data drive every number: POWER, SMAP, MODIS, ECOSTRESS, SRTM, GIBS; partner data: Sentinel-2, ERA5 | GPM IMERG and GRACE-FO are not integrated (no time to add Earthdata pipelines for them) → stated in DATA.md and ROADMAP #1 |
| **Presentation** | 4 | 30 s captioned video from real captures; 7-slide outline; README with screenshots from web, iOS and Android; one-command run; offline demo | No public live URL (owner's decision, ADR-014) → video plus `docker compose up` plus `FIELDSHIFT_OFFLINE=1` offline demo; screenshots from three platforms |

**Overall: 4.5 / 5.**

## Fixes made during the self-review pass
1. Demo presets were in town centres. Moved to real farm fields with outlines detected or traced on sub-metre imagery.
2. Sentinel-2 NDVI saturated at 1.0 (Earth Search offset double-applied). Fixed and re-run (EXP-11 in the commit history).
3. Water-allocation coverage note was always "100 %" (planner compared against allocation-limited use). Now compares with the full-irrigation need.
4. Mock-data screenshots from an early capture were all recaptured on real data. The capture scripts refuse to run when the MOCK banner shows.
5. Machakos and Córdoba pins were in towns, which gave urban terrain statistics. Fixed by (1).

## Known residual risks
- **Public data services.** ORNL subsets, SoilGrids and the AppEEARS queue can be slow or down. Mitigated by the cache, the fallback chain and the committed demo dataset.
- **Esri basemap licence** for production. ADR-015; NAIP and Sentinel-2 alternatives are wired in.
- **SMAP for arbitrary new fields** needs an asynchronous AppEEARS task. The demo fields are pre-extracted.
