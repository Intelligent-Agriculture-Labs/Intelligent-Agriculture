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
- **Yield.** FAO-33 Ky response with heat and frost penalties. No nutrient, pest, weed or variety effects.
  - **Level.** The level is calibrated to FAOSTAT national yields by crop and region (ADR-022, V10). On countries the calibration never saw, the simulated 2000–2024 mean is within ±30 % for 54 % of country × crop pairs; the held-out RMSLE is 0.50, about ±65 % typical error.
  - **Calibrated yields describe the typical farm in the region.** A well-managed field can yield much more, especially in sub-Saharan Africa (regional factor 0.39) and South/Southeast Asia.
  - **Where the level is still weak:**
    - Middle East & North Africa: irrigated Egypt and rain-fed Morocco/Türkiye share one factor; the held-out error was not reduced.
    - East Asia and Oceania: one benchmark country each; the held-out level is 20–40 % high.
    - Rice, sugarcane, cassava and potato: the regional gap explains little.
    - Crops without FAOSTAT series (vegetables, teff, cowpea, …) get only the regional factor. Alfalfa and forages are uncalibrated.
  - **Year-to-year.** The model reproduces droughts in water-limited rain-fed systems: U.S. 2012, Russia 2010, Kazakhstan 2012, southern Africa 2016, Pampas 2018/2023, Morocco 2007, Iberia 2005. Overall skill against national yields is low (median detrended r = 0.14), and near zero for irrigated and humid-tropical crops.
  - **Misses:** Argentina 2009, Ukraine 2020, Spain 2023, Germany 2018.
  - **Benchmark scope.** Benchmark sites are 1–3 POWER cells per country × crop with a loam default soil; national averages mix many more fields.
  - Scenario differences remain more meaningful than absolute yields (EXP-05).
- **Validation:**
  - Soil-water dynamics are weaker in East Africa (EXP-02).
  - Drought status at Fallon only moderately matches the USDM, because Nevada's farm drought is a water-supply (snowpack) drought (EXP-03). GRACE storage now gives regional water-supply context, but it does not enter the drought level (ADR-025).
  - The late-blight model ranked the 2009 epidemic year 3rd of 11 (EXP-07).
- **Disease models** use RH ≥ 90 % as a leaf-wetness proxy, from gridded data. They indicate *favourable weather*, not disease presence.
- **Global pest and disease models** (MODELS §5b, VALIDATION V11):
  - Leaf wetness is estimated from gridded RH ≥ 90 % (plus rain hours). In the humid tropics this is met almost every night, so the coffee-rust, Sigatoka and gray-leaf-spot scores saturate and cannot separate bad years from normal ones (V11 #4–6).
  - NASA POWER hourly replays lack terrain downscaling in the live replay path: mountain fields can be several °C off. The validation corrects this with a lapse rate; the replay mode does not.
  - BLASTAM's wetness came from AMeDAS rain, wind and sunshine; IA uses humidity. The stem-rust light requirement after dew is not modelled.
  - Some parameters are assumptions, not published constants, and are marked so in MODELS §5b: the Sigatoka Wmin of 12 h, the desert-locust warm factor and the 400 mm habitat limit, and the gray-leaf-spot 14-day pro-rating.
  - **Desert locust:** only rain at the field's own grid cell is used, while breeding happens in nearby deserts. The card is awareness only and points to FAO Locust Watch and national locust units.
  - **Coffee and banana are not IA crops yet,** so their models produce no cards.
  - **Northern leaf blight** was dropped because its published criteria could not be verified.
- **Pest degree-day thresholds** are literature values, mostly from North American extension services. Geographic ranges are coarse (continent level). Titles are translated; the per-stage action text is English-only.
- **Rotation scores** use transparent but simplified indices (soil-health index, RUSLE-inspired erosion index, pest-cycle score). They have not been calibrated against field trials.
- **Confidence values** are documented heuristics, not calibrated probabilities.

## Field mapping, satellite and AI components
- **Tap-to-detect** is measured worldwide (VALIDATION V15, 467 Fields of The World fields in 25 countries) but is not
  perfect. The outline must be checked and is always editable.
  - Smallholder plots (< 0.5 ha, typical of Kenya, Rwanda, India, Vietnam, Cambodia) remain the hardest case.
    Plot edges there are often thinner than one 2.7 m working pixel, and neighbouring plots look alike.
  - Very large fields (> 100 ha, e.g. Brazil: held-out IoU only 0.27) do not fit the zoom-16 window (~1.3 km)
    and come back partial. Large uniform fields with drainage lines or tramlines can also be cut into a smaller piece.
  - The learned edge model was trained on open orthophotos of four European countries only (France, Spain,
    Netherlands, Austria). It works on Esri imagery elsewhere (held-out countries in V15), but there is no
    training data from Africa, Asia or the Americas.
  - The benchmark compares with registered parcel polygons (LPIS and similar), whose year (2016–2023) differs from
    the unknown Esri image date. A parcel can also span or split visible fields. Scores are therefore a lower bound
    on agreement with what a farmer sees, and per-country numbers (12–32 fields each) carry wide error bars.
  - Confidence is the selector's predicted IoU. It ranks results usefully, but it is not a calibrated probability.
  - Some FTW source licences are non-commercial (Latvia, Portugal: CC-BY-NC-4.0; Lithuania: non-commercial use only;
    South Africa: CC-BY-NC-SA-4.0) or GPL (Kenya). These countries are used only for evaluation; their polygons are not
    redistributed and were not used for training.
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
