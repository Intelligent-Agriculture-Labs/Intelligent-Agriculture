# Limitations — honest list

## Data
- **Spatial scale.** Weather comes from NASA POWER's ~50 km grid, the forecast from ~10–25 km, SMAP at 9 km, MODIS NDVI at 250 m. None of them resolves a 1–10 ha field. Every card says so. Microclimates (frost hollows, valley winds, irrigated-canopy humidity) are not captured.
- **Irrigation history is unknown.** The model assumes the farmer irrigated when needed unless they enter their last irrigation (ADR-009). Satellite soil moisture cannot see irrigation on small fields in arid regions.
- **Rain (POWER + GPM IMERG).**
  - The 50/50 blend is served only between 45° S and 45° N; the 18 validation gauges span 35° S–42° N. Poleward, POWER's MERRA-2 rain is served unchanged.
  - IMERG Final arrives ~2–3 months late. For the most recent weeks the app uses POWER scaled by the local IMERG/POWER climatological ratio, which fixes the average amount but not the timing of individual storms.
  - Mountains: at Bogotá (2,550 m) both POWER and IMERG overestimate rain by +84 % / +98 % and the blend does not help; at Pune (lee of the Western Ghats) both overestimate strongly. Steep orographic rain is beyond both products.
  - The gauge test is not fully independent: IMERG Final is calibrated to GPCC monthly gauge analyses and MERRA-2's corrected rain to CPC gauges, and GHCN stations feed both.
  - Several tropical GHCN records are patchy (Nairobi 41, Bamako 38 usable months); their per-site numbers are indicative.
- **Regional water storage (GRACE/GRACE-FO).**
  - The footprint is ~300 km (one 3° mascon). It measures total water (groundwater + soil + surface water + snow), not the aquifer under the field.
  - A local well can disagree: at Fallon, 257 USGS wells are flat on median while GRACE's region is falling (irrigation recharge keeps the shallow aquifer up while the wider Great Basin dries). The card therefore says "regional water reserves" and asks the farmer to check their well.
  - Data arrive 2–3 months late, and there is no data from Jul 2017 to May 2018.
  - The asset is a snapshot (through Sep 2026); refreshing it needs Earthdata Login on the data box (`scripts/grace_extract.py`).
  - No current groundwater *percentile* yet (GRACE data-assimilation product blocked by the GES DISC EULA step).
- **Still without Earthdata-based products:** full ECOSTRESS and HLS 30 m NDVI (ROADMAP #1).
- **The ORNL subset API is slow and was intermittently down** during the build. Satellite layers (NDVI, MOD16, SMAP) may be missing for new locations. The cards degrade gracefully, and the demo farms are pre-cached.
- **SoilGrids is a 250 m estimate.** It is not a soil test. When it is unavailable, a loam default is used and labelled.
- **Prices and costs are national indicative values.** Gross margins are for comparing rotations, not for budgeting.

## Models
- **Single-Kc water balance.** Evaporation and transpiration are not separated (FAO-56 dual Kc would be better for sparse canopies and drip). Salinity and capillary rise from shallow groundwater are not modelled. The latter matters in parts of the Lahontan Valley.
- **Yield.** FAO-33 Ky response with heat and frost penalties, scaled to typical irrigated yields. No nutrient, pest, weed or variety effects. Absolute yields are indicative; scenario differences are more meaningful (EXP-05).
- **Validation:**
  - Soil-water dynamics are weaker in East Africa (EXP-02).
  - Drought status at Fallon only moderately matches the USDM, because Nevada's farm drought is a water-supply (snowpack) drought (EXP-03). GRACE storage now gives regional water-supply context, but it does not enter the drought level (ADR-021).
  - The late-blight model ranked the 2009 epidemic year 3rd of 11 (EXP-07).
- **Disease models** use RH ≥ 90 % as a leaf-wetness proxy, from gridded data. They indicate *favourable weather*, not disease presence.
- **Pest degree-day thresholds** are literature values, mostly from North American extension services. Geographic ranges are coarse (continent level). Event labels are English-only.
- **Rotation scores** use transparent but simplified indices (soil-health index, RUSLE-inspired erosion index, pest-cycle score). They have not been calibrated against field trials.
- **Confidence values** are documented heuristics, not calibrated probabilities.

## Field mapping, satellite and AI components
- **Tap-to-detect** merges or splits fields in some cases:
  - It can leak through gaps (farmsteads) into identical neighbouring crops.
  - It finds only one strip of terraced or intercropped smallholder plots.
  The outline must be checked and is always editable.
- **Imagery.** The default high-resolution basemap (Esri World Imagery) is used with attribution for this non-commercial demo; production needs a licence. USDA NAIP (U.S., public domain) and Sentinel-2 (10 m) are alternatives.
- **Sentinel-2 analysis:**
  - The first analysis of a new field takes ~30 s on a fast link and several minutes on a slow one.
  - Cloudy regions and seasons yield fewer clear scenes.
  - NDVI saturates over very dense canopies.
- **AI management zones** are statistical. Their causes (soil, water, pests, management) need ground truth; zones on small (< 1 ha) fields are noisy.
- **AI drought classifier.** It is served only in the contiguous U.S. (USDM labels). Elsewhere the rule-based status is used.
  - A global version trained on European (EDO CDI) and global soil-moisture (GDO) labels was validated on held-out regions and **not adopted** (EXP-11):
    - It narrowly lost to the current model in Europe.
    - Outside the U.S., both ML models lost to the rule-based blend on within ±1. They over-predict drought where label systems differ from USDM.
  - For Australia, South America, Africa and Asia, the only open, gridded, multi-decade labels found were a single modelled soil-moisture anomaly, which is weak. National categorical drought monitors (e.g. NADM, South Africa) were not integrated.
- **SMAP and ECOSTRESS series** exist only for the pre-extracted demo fields (asynchronous AppEEARS batch with Earthdata Login). New fields get MODIS/POWER-based indicators.
- **Accounts** have no e-mail verification and no self-service password reset (no mail server in this self-hosted deployment).
- **Farm sync by code** has no accounts. Anyone with the farm code can see and edit that farm's fields, so keep it private. There is no end-to-end encryption.

## Product
- The step-by-step "Why?" reasoning and pest event labels are English; card titles and details and the whole UI are translated into 6 languages.
- No user accounts or sync. Field data stays on the device.
- **Not deployed publicly** (requires the owner's decision; see DEPLOYMENT.md).
- The tool supports, and does not replace, farmer judgement and local agronomic advice.
