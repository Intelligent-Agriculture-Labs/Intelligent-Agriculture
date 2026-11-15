# Models and methods

The code lives in `backend/fieldshift/science/`; versioned parameters live in `backend/fieldshift/config/`. Equation numbers refer to FAO-56 (Allen et al., 1998) unless stated otherwise.

## <a id="et0"></a>1. Reference evapotranspiration (`et0.py`)
FAO-56 Penman–Monteith, daily (eq. 6):

ET₀ = [0.408 Δ (Rₙ − G) + γ (900 / (T + 273)) u₂ (eₛ − eₐ)] / [Δ + γ (1 + 0.34 u₂)]

- eₛ from Tmax/Tmin (eqs. 11–12); eₐ from dew point (eq. 14), falling back to RHmean (eq. 19) and then to Tdew ≈ Tmin.
- Δ (eq. 13); γ from elevation (eqs. 7–8; SRTM elevation).
- Rₙ = Rₙₛ − Rₙₗ with α = 0.23, Rₛₒ = (0.75 + 2·10⁻⁵ z) Rₐ, and Rₐ from latitude and day of year (eqs. 21–25, 37–39). G = 0.
- Inputs come from NASA POWER: `T2M_MAX`, `T2M_MIN`, `T2MDEW`, `WS2M` (already at 2 m), `ALLSKY_SFC_SW_DWN` (MJ m⁻² d⁻¹).
- Fallback when radiation is missing: Hargreaves–Samani (eq. 52).
- Tested against FAO-56 Examples 2, 8, 14 and 18 (`tests/test_et0.py`; Example 18 Uccle: 3.9 mm/d).

## <a id="water-balance"></a>2. Season model (`cropmodel.py`)
**Phenology (thermal time).**
- GDD = max(0, (min(Tmax, 30) + max(Tmin, Tbase))/2 − Tbase), with Tbase per crop (McMaster & Wilhelm, 1997, method 2).
- The thermal requirement is calibrated per location: GDDreq = mean over the last 15 years of ΣGDD across the crop's FAO-56 season length from the planting date. Progress f = ΣGDD / GDDreq.
- So a +ΔT scenario shortens the season, as it would for a fixed variety.

**Crop coefficient.** The FAO-56 four-stage single-Kc curve (Kc_ini, Kc_mid, Kc_end; stage fractions from Table 11), indexed by f.
- Alfalfa uses repeating cutting cycles (Table 11, "individual cutting periods"), with a cut every 420 °C·d (base 5 °C; ≈ 750 °F·d base 41 °F, the extension rule of thumb).
- The alfalfa season ends at the first killing frost after two months.

**Root-zone water balance** (eq. 85), daily: Dᵣ,ᵢ = Dᵣ,ᵢ₋₁ − Pᵢ − Iᵢ + ETc,adj,ᵢ + DPᵢ.
- TAW = θ-range × Zᵣ. θ-range by texture class (Table 19 mid-points); Zᵣ grows from Zmin to Zmax by the end of the development stage.
- RAW = p·TAW, with p adjusted by p + 0.04(5 − ETc) (Table 22 note).
- Kₛ = (TAW − Dᵣ)/((1 − p) TAW) when Dᵣ > RAW (eq. 84). ETc,adj = Kₛ·Kc·ET₀. Overflow becomes deep percolation.
- Mass closure is unit-tested.
- **Antecedent soil water (EXP-12).** By default (`antecedent_days=180`, annual crops), a fallow bucket over the full root zone runs from 180 days before sowing:
  - it starts at 60 % depletion (left by the previous crop);
  - evaporation is 0.3·ET₀·(1 − D/TAW_max) (stage-2 drying, FAO-56 Ch. 7);
  - rain refills it, and the excess drains.
  
  Its relative depletion sets the initial root-zone depletion. Soil reached by growing roots enters at that depletion instead of at field capacity, so a dry winter carries over into the season. With `antecedent_days=0`, or when the record is too short, the FAO-56 default applies: 30 % initial depletion, deeper soil at field capacity.

**Irrigation strategies.**
- *Full:* refill to field capacity when Dᵣ ≥ RAW.
- *Deficit 75 / 50:* trigger deeper (RAW + 25 % or 45 % of (TAW − RAW)) and refill to 25 % or 50 % depletion.
- *Allocation:* full strategy until the seasonal allocation is used up.
- *Split-season:* no irrigation after a date.
- Gross depth = net / efficiency: drip 0.90, pivot 0.85, sprinkler 0.75, furrow 0.60, flood 0.65 (well-managed border) (typical application efficiencies).

**Yield.**
- FAO-33 / FAO-56 yield response (eq. 90): 1 − Yₐ/Yₘ = Kᵧ (1 − ETₐ/ETₘ).
- Yₘ = typical yield × completion², where completion < 1 if a killing frost ends the season early. For alfalfa, Yₘ = typical yield × (cuts / 4.5).
- Heat: −3 % per day with Tmax ≥ T_heat in mid-season (cap −50 %).
- Frost before 80 % progress: −5 % (initial), −15 % (development), −35 % (mid-season). Frost after 80 % ends the season.
- Diagnostic biomass in the AquaCrop style: B = WP*·Σ(Tr/ET₀) (Steduto et al., 2009), reported for comparison (EXPERIMENTS.md).
- **Global calibration** (`science/yieldcal.py`, ADR-022, VALIDATION V10): Yₐ is multiplied by f_crop × f_region^s_crop from `config/yield_calibration.yaml`.
  - The factors are fitted to FAOSTAT national yields (263 country × crop pairs, 41 countries) and validated leave-one-country-out.
  - f_crop corrects the potential level per crop. It is fitted in Northern America, Western and Southern Europe, where f_region = 1.
  - f_region is the regional yield gap: sub-Saharan Africa 0.39, Southeast Asia 0.50, South Asia 0.62, Latin America 0.78, Eastern Europe & Central Asia 0.79, East Asia 0.86, MENA 0.88, Oceania 0.88.
  - s_crop scales the gap per crop: maize 1.68 and sorghum 1.96 (large gaps), cassava 0.60 and sugarcane 0.20 (small).
  - The region comes from a 0.5° country grid (MIRCA2000 units → UN M49). A location outside the grid, or a `Weather` without a region, is uncalibrated.
  - Annual crops without FAOSTAT series get f_region only; perennials, forages and cover crops get no factor.
  - Water use, irrigation and the year-to-year pattern are not calibrated, only the level.

**Assimilation hook.** `simulate(..., assimilate={date: Dᵣ_obs}, assimilation_weight=α)` nudges the state with Dᵣ ← (1 − α) Dᵣ + α Dᵣ_obs. It is used in the experiments with ERA5-Land; it is not on by default (EXPERIMENTS.md explains why).

## <a id="drought"></a>3. Drought (`drought.py`)
- **SPI-n** (McKee et al., 1993; WMO-No. 1090): n-day rain sums compared with the same calendar window (±7 days) in every year since 1984. Gamma fit (scipy, location fixed at 0), mixed with the probability of zero, then transformed to a normal quantile.
- **SPEI-n** (Vicente-Serrano et al., 2010): the same for P − ET₀, using empirical plotting positions.
- **Percentiles:** SMAP surface soil moisture against its own record; vegetation condition index VCI = (NDVI − NDVImin)/(NDVImax − NDVImin) per 16-day period since 2001.
- **Status:** a weighted blend of indicator levels, following the USDM-style convergence of evidence.
  - SPI thresholds: D0 ≤ −0.5, D1 ≤ −0.8, D2 ≤ −1.3, D3 ≤ −1.6, D4 ≤ −2.0.
  - Weights: SPI-90 0.30, SPEI-90 0.25, SPI-30 0.15, soil-moisture percentile 0.20, VHI 0.10, plus the long-term SPEI-12 at 0.30 (EXP-03).

## <a id="disease"></a>4. Disease risk (`disease.py`)
Hourly T and RH come from the forecast (validation uses POWER hourly). RH ≥ 90 % is the leaf-wetness proxy (Sentelhas et al., 2008).
- **Late blight, Hutton criteria** (AHDB 2017): two consecutive days with Tmin ≥ 10 °C and ≥ 6 h at RH ≥ 90 % → score 1.0. Near misses (4–5 h, or a single day) score 0.6, 0.3 or 0.15.
- **Stripe rust:** the longest run of wet hours at 7–15 °C; 8 h gives score 1 (de Vallavieille-Pope et al., 1995).
- **Powdery mildew:** ≥ 6 consecutive hours at 21–30 °C (Gubler et al., 1999, simplified).
- **White mould, alfalfa leaf diseases, millet downy mildew:** wet hours within a temperature window.
- Score → risk: ≥ 0.85 severe, ≥ 0.55 high, ≥ 0.25 moderate.

## <a id="pests"></a>5. Insect phenology (`pests.py`)
Degree-days = max(0, (min(Tmax, T_up) + Tmin)/2 − T_low), accumulated from a biofix of 1 January (northern hemisphere) or 1 July (southern).

| Pest | T_low / T_up (°C) | Events (°C·d) | Source |
|---|---|---|---|
| Alfalfa weevil | 9 / 30 | 156 egg hatch, 319 peak larvae, 450 decline | UC IPM; Purdue (48 °F base) |
| Western corn rootworm | 11.1 / 30 | 380 hatch, 570 peak injury, 760 adults | Iowa State Ext. |
| European corn borer | 10 / 30 | 208, 611 flights | Mason et al., 1996 |
| Corn earworm | 12.6 / 33.3 | 420 larvae | UC IPM |
| Colorado potato beetle | 10 / 30 | 105 adults, 300 larvae | Ferro et al., 1985 |
| Cereal aphids | 5 / 30 | 250 build-up | CSU Ext. (indicative) |
| Fall armyworm | 10.9 / 35 | 350 per generation | Hogg et al., 1982 |

## <a id="planting"></a>6. Planting-window optimisation
The season model runs for candidate dates (intended date ±35 days, weekly) over 15 past seasons. Score = median − 0.5 × (median − p10), which penalises bad-year downside. The recommended window is every date within 3 % of the best score.

## <a id="climate"></a>7. Climate trends (`climate.py`)
Yearly indicators from POWER (1984 → last complete year):
- warm-season Tmax, winter Tmin, GDD (base 10 °C), frost dates and frost-free days;
- days ≥ 35 °C, annual and warm-season rain, ET₀, water deficit;
- heavy-rain days (≥ the local 95th percentile of wet days), longest dry spell.

Trend: Theil–Sen slope per decade, with Mann–Kendall significance (Kendall's τ). An insight is shown only when p < 0.1.

## <a id="rotations"></a>8. Rotation explorer (`rotation.py`)
Candidates are the farmer's current rotation plus ten templates (`config/rotations.yaml`). Each slot is simulated over the last 15 seasons with the farmer's irrigation method, strategy and allocation. Planting dates are hemisphere- and tropics-aware: in the tropics, planting starts with the wettest 4-month window.

**Feasibility filter.** A strategy is dropped if any slot:
- has < 60 % valid seasons;
- has frost during the season in > 30 % of years; or
- has a median yield < 35 % of typical (too cold, short or dry).

**Metrics.**
- **Water:** mean gross irrigation (irrigated) or ETₘ − ETₐ shortfall (rain-fed), mm/yr. Scored relative to the other candidates (lower is better).
- **Income:** mean gross margin = yield × price − cost + 40 kg N/ha × $1.3 after a legume. Rotation effects:
  - −8 % yield for the same family in consecutive slots;
  - +5 % after a legume;
  - alfalfa seeding year × 0.7, then −10 %/yr after year 4 (stand decline / autotoxicity).
  Scored relative to the other candidates.
- **Soil-health index (0–100):** 40 % living-root months + 30 % residue class + 20 % biological N (cap 100 kg/ha/yr) + 10 % rooting-depth diversity.
- **Erosion (RUSLE-inspired, relative):** Σ months (1 − cover) × erosive-rain share of that month (rain on days ≥ the local 90th percentile), × LS factor (1 + slope%/5, slope from SRTM). Score = 100 × (1 − index/1.5).
- **Pest-cycle disruption:** 50 % family diversity + 50 % penalty on the longest same-family run.
- **Climate risk:** 0.5 × share of failed seasons (< 50 % of median) + 0.3 × heat/frost events + 0.2 × CV of margins.
- **Total score:** priority-weighted mean of the water, income, soil, pest and risk scores; the weights are the farmer's sliders.

**Texts.**
- *Why suggested* comes from the template idea.
- *Evidence* is generated from model numbers (POWER normals, simulated irrigation and yields, SRTM slope).
- *Benefits* lists metrics ≥ 8 points better than the current rotation.
- *Information gaps* and *risks for local review* are rule-based: market, soil test, low-confidence crop parameters, alfalfa autotoxicity, water-right rules, herbicide carry-over.

## <a id="terrain"></a>9. Terrain maps (`terrain.py`, `engine/maps.py`)
**DEM.** A 3 × 3 block of zoom-14 web-mercator terrain tiles (AWS Terrain Tiles, terrarium encoding: NASA SRTM 30 m outside the U.S., USGS 3DEP in the U.S.) is fetched around the field. That gives ~768 × 768 px of ≈ 9.5 m·cos(lat). The DEM is smoothed to the true source scale (~30 m) before derivatives, to avoid "orange-peel" artefacts from oversampling.

| Layer | Method |
|---|---|
| Slope, aspect | Horn (1981) 3 × 3 finite differences; aspect = compass bearing of the downslope direction |
| Hillshade | Burrough & McDonnell (1998); sun from 315° at 45° |
| Flow accumulation | D8 steepest descent (O'Callaghan & Mark 1984), cells processed from highest to lowest; no pit filling |
| Wetness | Topographic wetness index TWI = ln(a / tan β) (Beven & Kirkby 1979), with a = specific catchment area |
| Frost-prone hollows | Topographic position index TPI = z − mean(z within ~300 m) (Weiss 2001). Cold-air-pooling index = clip(−TPI / 8 m) × clip(1 − slope / 8°) |
| **Erosion (RUSLE)** | A = R · K · LS · C · P (Renard et al. 1997) |
| Management zones | Erosion hotspot (A ≥ 10 t/ha/yr, or the worst quarter of the field's at-risk area, so a uniformly erosive field still shows where to act first) > erosion risk (A ≥ 5 t/ha/yr, ≈ tolerable soil loss) > wet (top-10 % TWI on < 3 % slope) > frost hollow (index ≥ 0.5) > productive core, classified on ~90 m-smoothed indices |

RUSLE inputs:
- **R** from NASA POWER mean annual precipitation (Renard & Freimund 1994): R = 0.0483 P¹·⁶¹ for P ≤ 850 mm, else 587.8 − 1.219 P + 0.004105 P².
- **K** by soil texture: OMAFRA mid-values (Stone & Hilborn 2012).
- **LS** after Moore & Burch (1986): (A_s/22.13)^0.4 · (sin β / 0.0896)^1.3, with flow length capped at 120 m.
- **C** by crop type: perennial 0.02, cover 0.05, small grain 0.20, row crop 0.38.
- **P** = 1 (no support practices).

Field statistics use the drawn polygon, or a 150 m radius around the pin.

## <a id="planner"></a>10. Season planner (`engine/planner.py`)
For the next occurrence of the planting date, the season model runs for each of the last 15 seasons:
- **Sowing-date scan:** ±6 weeks in weekly steps, giving median and p10 yield, irrigation, frost risk and heat days. Recommended window as in §6.
- **Stage dates:** median days to the FAO-56 stage boundaries in thermal time, with the 10–90 % spread between years. Perennials get the median cutting dates instead.
- **Pest scouting:** median calendar dates of the first two degree-day events of every pest present in the region.
- **Monthly water budget:** median ET₀, ETc, ETa, rain and gross irrigation per month. With an allocation, the full-irrigation need is simulated too, and coverage = allocation / full need.
- **Risk calendar:** share of years with a damaging frost (crop kill threshold) or ≥ 3 heat days (≥ T_heat) in each month.

## <a id="field-detect"></a>11. Tap-to-detect field boundaries (`science/fielddetect.py`)
The farmer taps inside a field, and an editable polygon comes back in ~0.5–3 s.

**Imagery.** Sub-metre RGB (Esri World Imagery; USDA NAIP option in the U.S.), a 3 × 3 tile window at zoom 17, retrying at zoom 16 if the field touches the window edge.

**Pipeline:**
1. Downsample to ~2.7 m and apply a 5 × 5 median filter, which removes crop rows and wheel tracks.
2. Convert to CIE-Lab.
3. Felzenszwalb–Huttenlocher graph segmentation (scale 300).
4. Snap the tap to the lowest-gradient pixel nearby.
5. Edge-aware region growing over adjacent segments. A segment joins when ΔE(segment, region mean) < 9 **and** the median gradient along the shared border is below max(90th-percentile gradient, 5). Roads and ditches stop the growth; internal irrigation borders do not.
6. Fill holes, morphological opening, keep the component containing the tap.
7. Trace the contour and simplify it (Douglas–Peucker, 2 px).

**Confidence** = f(boundary contrast, compactness, border contact).

**Visual check on real farms:**
- Fallon border-irrigated field and Córdoba wheat field: outlined correctly.
- Iowa: correct, with one leak through a farmstead gap.
- Terraced smallholder plots (Machakos): only one strip is found.

That is why the polygon always stays editable.

## <a id="satellite"></a>12. Field satellite analytics (`science/satellite.py`, `engine/satellite_service.py`)
**Data.** Sentinel-2 L2A COGs (Earth Search STAC) from the last 12 months, cloud cover < 60 %, up to 24 scenes spread over time. Bands red, NIR and SCL are read through a GDAL WarpedVRT onto a ~10 m web-mercator grid around the field, so scenes from different UTM tiles stack pixel-for-pixel and align with the map. Clear pixels are SCL classes 4/5/6; a scene counts only if ≥ 60 % of the field is clear.

**NDVI series.** Daily linear gap-filling, then a Savitzky–Golay filter (window 31 d, order 2; Chen et al. 2004).

**Phenology.**
- Green-up and senescence at 50 % of the seasonal amplitude (TIMESAT; Jönsson & Eklundh 2004).
- Bare periods: NDVI < 0.20 for ≥ 20 days.
- Season type from prominent peaks (prominence ≥ 0.15): single season, double crop, or repeated cuttings such as alfalfa.

**AI management zones (unsupervised ML).**
- Standardized per-pixel features: mean NDVI, peak NDVI (p90), temporal NDVI variability, slope and wetness (TWI, from the DEM resampled onto the same grid).
- k-means with k ∈ {2, 3, 4} chosen by silhouette score (Rousseeuw 1987); the smallest k wins unless a larger k separates clearly better.
- Zones are ranked by vigour.
- Advice rules use zone wetness and slope relative to the field (waterlogging vs. thin soil on slopes vs. sampling).

**Satellite crop coefficient.**
- fc = (NDVI − 0.15)/(0.85 − 0.15).
- Kcb = 0.15 + (Kcb_full − 0.15) · min(1, 1.5 fc, fc^(1/(1+h))), the FAO-56 density coefficient (Allen & Pereira 2009).

**Data fusion into the water balance.** If a clear scene ≤ 15 days old exists for the field, crop water use from that date is scaled by (Kcb_sat + 0.05)/Kc_model, clipped to 0.4–1.4. The irrigation card's Why shows the numbers, and its confidence rises by 0.1.

## <a id="drought-ml"></a>13. AI drought classifier (`science/drought_ml.py`, `scripts/train_drought_ml.py`)
**Features** (the same code for training and serving), daily from NASA POWER:
- SPI-30/90/180/365 (gamma fit per week-of-year);
- SPEI-like indices on P − ET₀ for the same windows (Gringorten empirical probabilities);
- 30/90-day Tmax anomalies;
- seasonality (sin/cos day of year);
- aridity (ΣP/ΣET₀).

**Labels.** The dominant weekly U.S. Drought Monitor category per county (highest Dk covering ≥ 50 % of the area): 80 counties stratified across the contiguous U.S., 2005–2024, 83,600 samples.

**Model.** scikit-learn HistGradientBoostingClassifier: class-balanced, 300 iterations, learning rate 0.06, 31 leaves, L2 1.0.

**Evaluation.** 5-fold GroupKFold by county, i.e. on counties the model never saw, against the rule-based status on the same samples (EXP-09).

**Use.** The model is used only inside its validated domain (contiguous U.S.), where it replaces the rule level; class probabilities are shown in the Why. Everywhere else the transparent rule-based status is used.

**Global extension (EXP-11, evaluated, not adopted).**
- `scripts/drought_labels_global.py` builds labels for 310 sites in seven regions:
  - U.S.: USDM;
  - Europe: EDO Combined Drought Indicator;
  - Australia, South America, Sub-Saharan Africa, South Asia and East Asia: GDO soil-moisture anomaly, a weak label with thresholds calibrated against USDM.
- `drought_ml.feature_matrix_v2` computes location-agnostic features:
  - SPI/SPEI;
  - lagged SPEI-90;
  - Tmax z-scores;
  - season phase from the locally warmest week;
  - climatological wet-season share and 90-day rain;
  - aridity, mean Tmax and rain seasonality.
- `scripts/train_drought_ml.py` validates with county CV in the U.S., leave-one-region-out and leave-one-climate-zone-out. It adopts a new model only under the rule in EXP-11.
- The run did not meet that rule (Europe held out was slightly worse), so the shipped model and its metadata are unchanged.
- Serving reads `feature_set`, `model_regions` and `served_key` from the metadata:
  - A future adopted model would be served only in the regions where it beat the rules on held-out sites. The region boxes are in `drought_ml.REGION_BOXES`.
  - Old metadata without these fields means: v1 features, U.S. only.

## <a id="sync"></a>14. Farm sync
An account-free farm document (SQLite) is addressed by a random 128-bit id, which stays secret on each device, plus an 8-character pairing code (alphabet without 0/O/1/I). Fields merge per id by `updated_at` (last writer wins); deletions are tombstones. The client pushes 2 s after a change and pulls on start, on focus and every 60 s.

## <a id="rotation-plan"></a>15. Per-field multi-year rotation plan (`science/rotation_plan.py`, `engine/plan_service.py`)
**Inputs.** Field location, outline and irrigation, the farmer's crop history (past years) and plan (next 1–8 years, main crop plus optional cover crop), and priorities.

**Knowledge base** (`config/rotation_knowledge.yaml`, documented in `docs/ROTATION_SCIENCE.md` with references):
- per-crop minimum return interval, self-tolerance and family interval;
- residual N effect and preceding-crop value;
- good/poor predecessors and allelopathy;
- soil-borne pathogens and pests with host lists, survival and recommended break years;
- general rules with yield effects (e.g. cereal after cereal).

**Per year:**
1. **Return interval:** a gap below the minimum is a *problem* if ≤ half the minimum, otherwise a *caution*. Yield effect from the rule table (default −10 %).
2. **Family interval.**
3. **Pathogen pressure:** for each rotation-controllable soil- or residue-borne organism hosted by the crop:
   - *High* if a host grew last year, or ≥ 2 host years within the published break (`break_years`).
   - *Medium* if one host year falls within the break.
   - *Low* if hosts are older but within `survival_years`.
   - Yield effect −12 % (high) or −5 % (medium), weighted by severity. Only high-severity organisms at high pressure make a year a red "problem".
   - Excluded as not rotation-controllable: generalists (Rhizoctonia, Pythium, root-knot nematodes) and the migratory fall armyworm. Wireworms are handled by the cited "after grass/ley" rule.
   - Regional ranges: Striga (Africa/Asia), corn rootworm (North America/Europe), broomrape, cereal stem borers, black-grass.
   - **Cited sequence rules** (`applies_to` × `after` within `window_years`, e.g. continuous maize −13 %, legume before cereal +20 %, Striga trap crops +15 %) carry their published effect. The generic return-interval and predecessor-value effects (+15/+5/−5 %, Saxon yield classes) apply only when no cited rule matched, to avoid double counting.
   - Continuing perennial stands are not "crop after itself"; only stand age is checked.
4. **Predecessor effect:** +5 % after good predecessors or high-value preceding crops, −5 % after poor ones. Allelopathy notes.
5. **N carry-over:** the previous crop's residual N plus 50 % of the cover crop's fixation. Fertiliser saving is valued at $1.3/kg N.
6. **Simulation:** the season model over 15 seasons at the field (median and p10 yield, irrigation, ET, failure share), scaled by the rotation effect (clipped to −45…+15 %). Perennial establishment year at 70 %.
7. **Bare-soil days:** 365 − (crop season + cover-crop season). RUSLE soil loss uses the field's R·K·LS (from the terrain analysis of the drawn outline) times the crop's C (×0.6 with a cover crop).
8. **Water:** irrigation need vs. allocation; rain-fed failure share.
9. **Climate fit:** feasibility from frost share, complete seasons and yield level.

**Score** = priority-weighted mean of five 0–100 components (pests and diseases, soil, water, income, climate risk), minus 0.4 × (25 per problem, 10 per caution).

**Suggestions:** for every year that is not "good", the best single-crop replacement among climate-feasible crops, plus "add a cover crop" where the soil lies bare. Only gains are shown.

**Regional cropping systems** (temperate, irrigated arid, Mediterranean, tropical) limit the optimiser and the suggestions to crops grown in that kind of climate, plus the farmer's own crops. Plans that drop the farm's main (staple) crop entirely get a 15-point penalty.

**Optimiser:** beam search (width 24, at most 3 states per last crop) over climate-feasible candidates. A cover crop is added automatically after short-season crops, chosen so it shares no family or pathogen with the next cash crop. The **farm-type constraint**: perennial forage, vegetables and roots/tubers are only proposed if the farm already grows that kind of crop, because of markets, machinery and labour.

## 16. Accounts and sync
- E-mail + password accounts: scrypt (n = 2¹⁴, r = 8, p = 1) with a 16-byte salt; constant-time verification.
- Sessions are random 256-bit tokens stored as SHA-256 hashes, valid 90 days.
- Login is rate-limited (8 failures per 15 min per e-mail).
- Each account owns one farm document (fields, history, plans, settings), merged per field by `updated_at`.
- The account-free sync code remains for sharing a farm.

## 17. Recommendation engine (`engine/service.py`, `config/rules.yaml`)
Each module emits zero or more cards, each with risk, due date and a Why block (summary, steps with numbers, series, model, confidence, caveats, sources). Cards are ranked by risk, then due date. Thresholds are versioned in `rules.yaml`, and texts in six languages are in `messages.yaml`.

**Confidence** is a documented heuristic, not a calibrated probability:
- water balance 0.55, or 0.70 if the farmer entered their last irrigation;
- drought 0.6 with ≥ 3 indicators, else 0.45;
- disease 0.5; pests 0.55; NDVI 0.45; frost/heat 0.6.

## <a id="rain-onset"></a>18. Rain-season onset, false starts and sowing windows (`science/onset.py`, `engine/rain_season.py`)
For rain-fed farmers in the tropics and monsoon regions, *when* to sow matters more than almost anything else. Sowing at the first shower risks losing seed and seedlings to a dry spell (a **false start**); sowing late shortens the season. Parameters live in `config/onset.yaml`; ADR-021 records the choices.

**Climatological seasons (both hemispheres, one or two per year).**
- The daily rain climatology (complete years since 1984, 31-day circular smoothing) is scanned for runs above the annual mean. This is where the anomalous accumulation rises, i.e. the climatological onset and cessation of Liebmann et al. (2012).
- Two rainy seasons are kept when the 2nd harmonic of the climatology is stronger than the 1st (Dunning, Black & Allan 2016), e.g. Machakos (ratio 1.5: MAM "long rains" and OND "short rains"). Otherwise the largest run is the one season.
- Seasons that cross New Year (southern hemisphere, e.g. Darwin NDJFMA) need no special case: each season instance is anchored at its climatological onset date in a given year.

**Per-year onset (Sivakumar 1988; Stern, Dennett & Garbutt 1981).** The first day of a 3-day period with ≥ 20 mm, starting with a wet day (≥ 1 mm), with no dry spell longer than 7 days in the following 30 days. The search runs from 45 days before to 60 days after the climatological onset (shorter when the season is short or the gap to the previous season is small). No valid onset in that window = a **failed season**.

**False start.** An *apparent* onset (the rain part of the criterion) followed by a dry spell > 7 days within 30 days. The site's false-start probability is the share of seasons whose first apparent onset was false.

**Cessation (Stern et al. 1981; Frère & Popov 1979, FAO).** A 100 mm soil store filled by rain and emptied by FAO-56 ET₀ (from NASA POWER). The season ends on the first day the store is empty, but not earlier than onset + 20 days or 3 weeks before the climatological end of the rains. This mirrors the fixed "earliest end date" of the Instat implementations. The 3-week offset was set on Machakos before any reference data were collected: an earliest end at mid-season piled the cessations onto that bound and gave median seasons of only 42–54 days. It was not fitted to the validation references. A store that runs dry is only taken as the end if no onset-sized rain (20 mm in 3 days) refills it within 21 days. Mid-season dry spells, common in semi-arid bimodal climates such as Machakos, otherwise ended the season too early; without this rule, the median Machakos OND end was 19 Dec instead of 3 Jan. The Sahel season-length check moved from MAE 12.7 to 12.5 days with the rule.

**Climatology product (`GET /api/rain-season`).** Per season:
- onset and cessation dates (p10–p90) and season length;
- false-start and failed-season percentages, and every year's onset, cessation and false starts;
- trends since 1984: Theil–Sen slope with Mann–Kendall p for onset, cessation and length, and false-start shares before vs. since 2005. These feed the "Field Shift" climate story, e.g. at Machakos the MAM season shortened by 6 days per decade (p = 0.07), and false starts rose from 15 % of years before 2005 to 40 % since.

**Live status ("this season" card, id `rain_onset`).** Observations, the Open-Meteo bridge and the 16-day forecast are scanned from the search window onwards. The phase is one of `before`, `not_started` (or late after the p80 onset), `forecast` (the rain criterion is met only in forecast days), `started`, `false_start`, `established` (30 days without a damaging spell), `ended` or `failed`.
- For `started`, the false-start risk is **conditional**: among all historical apparent onsets within ±20 days of this date's place in the season, the share followed by a damaging dry spell, given that none occurred in the days already checked (observed + forecast).
- The risk then sets the advice: below 20 %, sow now; 20–40 %, sow with care (moist to a hand's depth, keep seed to re-sow); 40 % or more, wait.

**Sowing windows per crop.** A crop must reach the end of its mid-season (grain fill; FAO-56 stage lengths) before the water-balance end of the season. The late (ripening) stage can run on stored water.
- `fit_pct`: share of past seasons in which sowing on the start date (onset, or expected median onset) would have achieved that.
- `sow_until`: last date that still works in 8 of 10 seasons.
- `max_variety_days`: the longest total cycle that fits in 8 of 10 seasons. When the field's crop does not fit, the card names an early variety (≤ N days) or a shorter crop.

**Where it is offered.** Rain-fed fields with |latitude| ≤ 35°, at least one rainy season and a real dry season: ≥ 60 days with climatological rain < ½ ET₀, the FAO agro-ecological-zones growing-period rule. Fallon, Córdoba and Ames therefore get no card; the API still returns the climatology with `applicable: false` and the reason.

**Planner.** For such fields, the planner's sowing-date scan is extended to cover the onset-based window. Every candidate gets `onset_ok`: on or after the median onset (rains have started in ≥ half of years) and no later than the latest sowing date. The recommended window is chosen only among `onset_ok` dates.

**Validation.** See [VALIDATION.md, V9](VALIDATION.md#v9).

## Optional LLM phrasing layer
Behind the flag `FIELDSHIFT_LLM_EXPLAIN` (off by default; not required). It is not implemented in v1; see ROADMAP.md. All texts are template-generated from computed numbers, so nothing is invented.

## References
- Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998) *Crop evapotranspiration*, FAO Irrigation and Drainage Paper 56.
- Doorenbos, J., Kassam, A.H. (1979) *Yield response to water*, FAO Irrigation and Drainage Paper 33.
- Steduto, P. et al. (2009) AquaCrop — the FAO crop model. *Agronomy Journal* 101: 426–437.
- McKee, T.B., Doesken, N.J., Kleist, J. (1993) The relationship of drought frequency and duration to time scales. 8th Conf. Applied Climatology.
- Vicente-Serrano, S.M. et al. (2010) A multiscalar drought index sensitive to global warming: SPEI. *J. Climate* 23: 1696–1718.
- Svoboda, M. et al. (2002) The Drought Monitor. *BAMS* 83: 1181–1190.
- AHDB (2017) Hutton criteria for potato late blight.
- Sentelhas, P.C. et al. (2008) Suitability of relative humidity as an estimator of leaf wetness duration. *Agric. For. Meteorol.* 148: 392–400.
- de Vallavieille-Pope, C. et al. (1995) Comparative effects of temperature and interrupted wet periods on germination, penetration, and infection of *Puccinia recondita* and *P. striiformis*. *Phytopathology* 85: 409–415.
- Gubler, W.D. et al. (1999) Control of powdery mildew using the UC Davis powdery mildew risk index. APSnet.
- McMaster, G.S., Wilhelm, W.W. (1997) Growing degree-days: one equation, two interpretations. *Agric. For. Meteorol.* 87: 291–300.
- Sen, P.K. (1968) Estimates of the regression coefficient based on Kendall's tau. *JASA* 63: 1379–1389.
- Fry, W.E. et al. (2013) The 2009 late blight pandemic in the eastern United States. *Plant Disease* 97: 296–306.
- Sivakumar, M.V.K. (1988) Predicting rainy season potential from the onset of rains in Southern Sahelian and Sudanian climatic zones of West Africa. *Agric. For. Meteorol.* 42: 295–305.
- Stern, R.D., Dennett, M.D., Garbutt, D.J. (1981) The start of the rains in West Africa. *J. Climatology* 1: 59–68.
- Frère, M., Popov, G.F. (1979) *Agrometeorological crop monitoring and forecasting*. FAO Plant Production and Protection Paper 17.
- Liebmann, B. et al. (2012) Seasonality of African precipitation from 1996 to 2009. *J. Climate* 25: 4304–4322.
- Dunning, C.M., Black, E.C.L., Allan, R.P. (2016) The onset and cessation of seasonal rainfall over Africa. *J. Geophys. Res. Atmos.* 121: 11405–11424.
- FAO (1978) Report on the Agro-ecological Zones Project, Vol. 1: Methodology and results for Africa. World Soil Resources Report 48.
