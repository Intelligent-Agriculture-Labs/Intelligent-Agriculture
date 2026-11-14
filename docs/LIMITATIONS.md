# Limitations — honest list

## Data
- **Spatial scale.** Weather comes from NASA POWER's ~50 km grid, the forecast from ~10–25 km, SMAP at 9 km, MODIS NDVI at 250 m. None of them resolves a 1–10 ha field. Every card says so. Microclimates (frost hollows, valley winds, irrigated-canopy humidity) are not captured.
- **Irrigation history is unknown.** The model assumes the farmer irrigated when needed unless they enter their last irrigation (ADR-009). Satellite soil moisture cannot see irrigation on small fields in arid regions.
- **No Earthdata Login.** GPM IMERG, GRACE-FO, full ECOSTRESS and HLS 30 m NDVI are not used yet (ADR-004). Rain comes from POWER's MERRA-2 bias-corrected precipitation.
- **The ORNL subset API is slow and was intermittently down** during the build. Satellite layers (NDVI, MOD16, SMAP) may be missing for new locations. The cards degrade gracefully, and the demo farms are pre-cached.
- **SoilGrids is a 250 m estimate.** It is not a soil test. When it is unavailable, a loam default is used and labelled.
- **Prices and costs are national indicative values.** Gross margins are for comparing rotations, not for budgeting.

## Models
- **Single-Kc water balance.** Evaporation and transpiration are not separated (FAO-56 dual Kc would be better for sparse canopies and drip). Salinity and capillary rise from shallow groundwater are not modelled. The latter matters in parts of the Lahontan Valley.
- **Yield.** FAO-33 Ky response with heat and frost penalties, scaled to typical irrigated yields. No nutrient, pest, weed or variety effects. Absolute yields are indicative; scenario differences are more meaningful (EXP-05).
- **Validation:**
  - Soil-water dynamics are weaker in East Africa (EXP-02).
  - Drought status at Fallon only moderately matches the USDM, because Nevada's farm drought is a water-supply (snowpack) drought (EXP-03).
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
- **AI drought classifier.** Trained and validated only for the contiguous U.S. (USDM labels). Elsewhere the rule-based status is used.
- **SMAP and ECOSTRESS series** exist only for the pre-extracted demo fields (asynchronous AppEEARS batch with Earthdata Login). New fields get MODIS/POWER-based indicators.
- **Farm sync** has no accounts. Anyone with the farm code can see and edit that farm's fields, so keep it private. There is no end-to-end encryption.

## Product
- The step-by-step "Why?" reasoning and pest event labels are English; card titles and details and the whole UI are translated into 6 languages.
- No user accounts or sync. Field data stays on the device.
- **Not deployed publicly** (requires the owner's decision; see DEPLOYMENT.md).
- The tool supports, and does not replace, farmer judgement and local agronomic advice.
