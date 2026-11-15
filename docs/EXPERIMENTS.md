# Experiments log

Each entry: hypothesis · method · data · metric · result · decision. Numbers come from `scripts/validate.py` runs on the VPS (`docs/validation/results.json`).

## EXP-01 ET₀ from NASA POWER is good enough to drive irrigation advice
- **Hypothesis:** FAO-56 PM computed from POWER daily inputs agrees with an independent FAO-56 ET₀ from ERA5 within ~10 % on a monthly basis.
- **Method:** daily ET₀ 2015–2024 at 4 sites; compared with Open-Meteo's ERA5 FAO-56 ET₀ (daily and monthly sums).
- **Result:**

  | Site | Daily r | Monthly r | Daily bias (mm/d) |
  |---|---|---|---|
  | Ames | 0.97 | 0.99 | −0.14 |
  | Córdoba | 0.98 | 0.997 | +0.01 |
  | Fallon | 0.97 | 0.996 | −0.48 |
  | Machakos | 0.86 | 0.91 | +0.56 |

  Fallon is 11 % lower than ERA5. ERA5's grid cell over the Lahontan Valley includes more hot desert; POWER's 0.5° cell also mixes desert and irrigated land, so neither is "the field". Machakos is 14 % higher than ERA5: tropical radiation and humidity differ between the products.
- **Decision:** keep POWER-PM as the backbone (NASA data, no key, 1984→). Show "~50 km grid" caveats. For irrigation amounts in the tropics, state lower confidence. Recalibrating ET₀ against ERA5 was rejected, because ERA5 is itself a model and not ground truth.

## EXP-02 The rain-fed water balance tracks soil-moisture dynamics
- **Hypothesis:** the bucket model's relative root-zone water (1 − Dr/TAW) correlates with ERA5-Land soil moisture (7–100 cm, weighted) during the season.
- **Method:** rain-fed seasons 2015–2023, maize at Ames and Machakos, winter wheat at Córdoba; Pearson r per season and pooled on standardized values.
- **Result:**

  | Site | Median r per season | Pooled r |
  |---|---|---|
  | Ames | 0.71 | 0.58 |
  | Córdoba | 0.73 | 0.72 |
  | Machakos | 0.50 | 0.30 |

- **Decision:** the dynamics are realistic in temperate climates. Machakos is weak: two short rainy seasons, POWER rain at 50 km, and ERA5-Land's own known biases in East Africa. Kenya advice therefore carries lower confidence, documented in LIMITATIONS.md. Assimilation of ERA5-Land or SMAP stays off by default: on a 1–10 ha field, assimilating a 9 km signal would be swapping one coarse estimate for another. The hook is implemented for future in-situ sensors.

## EXP-03 Adding a 12-month indicator improves drought status vs. the U.S. Drought Monitor
- **Hypothesis:** USDM integrates long-term hydrology (snowpack, reservoirs, groundwater), especially in the West. A drought status built only from 30–90-day indicators under-detects it.
- **Method:** weekly 2005–2024, Churchill County NV (Fallon) and Story County IA (Ames). Spearman ρ between the IA indicator and the USDM DSCI; hit rate and false-alarm ratio (FAR) for "≥ D1 over the county".
- **Result:**

  | Site | Indicator | ρ | Hit rate | FAR |
  |---|---|---|---|---|
  | Fallon | SPI-90 | 0.14 | | |
  | Fallon | SPEI-90 | 0.29 | | |
  | Fallon | SPEI-12 | 0.67 | | |
  | Fallon | **Status v1** (30/90-day) | 0.22 | 0.38 | 0.35 |
  | Fallon | **Status v2** (+ SPEI-12) | **0.38** | 0.42 | **0.25** |
  | Ames | SPEI-90 | 0.70 | | |
  | Ames | SPEI-180 | 0.74 | | |
  | Ames | **Status v1** | 0.66 | 0.69 | 0.44 |
  | Ames | **Status v2** | **0.74** | 0.68 | **0.37** |

- **Decision:** adopted v2 (SPEI-12 at weight 0.30). Fallon remains the weaker site. Nevada farm drought is a *water-supply* drought, driven by Sierra snowpack and the Truckee–Carson system, which local rain cannot see. Roadmap: add GRACE-FO water storage and snowpack once Earthdata credentials are available.

## EXP-04 Late-season frost should end the season, not destroy the yield
- **Observation:** in the first validation run, simulated rain-fed maize at Ames gave **0 t/ha in 1992, 1993 and 2009**. Those were cool but good harvest years. Cause: every fall frost after the crop was nearly mature added a 30 % penalty.
- **Change:** a frost after 80 % thermal progress now ends the season (harvest at current completion). Earlier frost costs 5 % in the initial stage, 15 % in development and 35 % in mid-season, with a floor of 20 % of potential.
- **Result:** 1992/1993/2009 now give 8.2–8.3 t/ha, near the median of 8.9. The documented drought years now rank **2012 = worst** and **1988 = 2nd-worst of 40** (previously 5th and 6th).
- **Decision:** adopted.

## EXP-05 Alfalfa cutting interval
- **Observation:** with a cut every 420 °C·d (base 5 °C), the model produced ~7 cuts per year and 24.8 t/ha at Fallon. Great Basin growers typically take 4–5 cuttings.
- **Change:** 600 °C·d per cutting; typical yield 13 t/ha at 4.5 cuts.
- **Result:** median 14.4 t/ha with full irrigation and 1,114 mm ET. This is of the order commonly reported for irrigated alfalfa in western Nevada (~1 m/yr). It will be cross-checked in EXP-06 (MOD16).
- **Decision:** adopted. Absolute alfalfa yields remain indicative; the rotation explorer uses them only relative to alternatives.

## EXP-06 Model ET vs. MODIS MOD16 (pending)
- ORNL DAAC returned 502/503 during the first run. It will be rerun after the satellite cache job completes (see VALIDATION.md for the final status).

## EXP-07 Late-blight risk in a documented epidemic year
- **Hypothesis:** Hutton criteria computed from NASA POWER hourly T/RH flag 2009 as a high-risk season in the U.S. Northeast. 2009 had a region-wide late-blight epidemic (Fry et al., 2013).
- **Result:** Ithaca NY, Jun–Aug: 2009 had 57 Hutton days, ranking **3rd of 11 seasons (2005–2015)**. 2008 (62) and 2006 (60) were wetter on POWER's grid. 2009's epidemic was amplified by infected transplants sold region-wide, which no weather model can see.
- **Decision:** keep the Hutton model (the operational UK standard), but present it as "weather favourable for infection", never as "disease present". The Hutton thresholds are calibrated for station RH; the 50 km grid RH is smoother, which inflates near-saturation hours. Card confidence is therefore 0.5.

## EXP-09 Does a learned drought classifier beat the rule-based blend?
- **Hypothesis:** gradient-boosted trees on multi-scale SPI/SPEI and temperature features from NASA POWER reproduce the U.S. Drought Monitor better than the hand-weighted blend, including at locations they never saw.
- **Method:** 80 counties, 2005–2024 weekly, 83,600 samples. 5-fold GroupKFold by county. Same samples for both methods.
- **Result (held-out counties):**

  | Metric | ML | Rules |
  |---|---|---|
  | Exact category | **0.61** | 0.59 |
  | Within ±1 category | **0.889** | 0.862 |
  | MAE (levels) | **0.54** | 0.60 |
  | Spearman vs DSCI | **0.68** | 0.55 |
  | D1+ hit rate | **0.70** | 0.45 |
  | D1+ false-alarm ratio | **0.39** | 0.42 |

- **Decision:** adopted for the contiguous U.S. (the validated domain), with probabilities shown. Outside the U.S. the rules stay, because transferring the model there is unvalidated.

## EXP-11 Can the drought classifier work outside the U.S.? (not adopted)
- **Question:** the EXP-09 classifier was trained and validated on U.S. counties only, so it is served only in the contiguous U.S. Could it be made accurate worldwide? We tested this with labels from other continents, location-agnostic features and block cross-validation that holds out whole regions.
- **Labels** (`scripts/drought_labels_global.py`; sources and licences in DATA.md):
  - **U.S.:** USDM, the same 80 counties as EXP-09.
  - **Europe:** EDO Combined Drought Indicator v4.1, 80 sites, 2012–2024. Watch → D0, Warning → D1, Alert → D2+. Recovery → None; the temporary-recovery classes → D0. Each 0.5° box uses the same ≥ 50 %-area rule as the USDM labels.
  - **Australia, South America, Sub-Saharan Africa, South Asia, East Asia:** 30 sites each, labelled from the GDO Soil Moisture Index Anomaly (2005–2024). This is a *weak* label: a single modelled indicator. Its D0–D4 thresholds are calibrated on the U.S. sites so that exceedance rates match USDM.
  - **How weak:** the SMIA label agrees with USDM at within ±1 0.84 and Spearman 0.49, and with CDI at within ±1 0.89 and Spearman 0.54.
- **Features v2** (`drought_ml.feature_matrix_v2`), each relative to the site's own climate:
  - multi-scale SPI/SPEI, plus SPEI-90 three months earlier;
  - Tmax anomalies as z-scores instead of °C;
  - season phase measured from the locally warmest week, which replaces calendar day of year and works in both hemispheres;
  - the climatological share of annual rain falling in the current 90-day window, and that rain in mm;
  - aridity P/ET₀, mean Tmax and Walsh–Lawler rain seasonality.
- **Validation** (`scripts/train_drought_ml.py`, 310 sites, 229,040 labels):
  - U.S.: GroupKFold(5) by county; the global model also trains on all non-U.S. data.
  - Every other region: leave-one-region-out.
  - Climate zones (arid / tropical / temperate / cold): leave-one-zone-out.
  - Transfer tests: Europe → U.S. and U.S. → Europe.
  - Non-U.S. regions are compared on a harmonised None / D0 / D1 / D2+ scale.
- **Adoption rule, declared before the first run:**
  - U.S. within ±1 and Spearman must be at least as high as the current model's;
  - **and** on held-out Europe and on the pooled weak-label regions, both must be higher.
- **Result** (full tables in VALIDATION.md V8). "Current" = the U.S.-only model in production; "global" = the v2 class-balanced model.

  | Held-out set | Within ±1: current / global / rules | Spearman: current / global / rules |
  |---|---|---|
  | U.S. counties (native D0–D4; Spearman vs. DSCI) | 0.879 / **0.894** / 0.862 | 0.654 / **0.687** / 0.548 |
  | Europe (CDI) | 0.859 / 0.847 / **0.887** | 0.493 / 0.488 / **0.526** |
  | Australia (SMIA) | 0.647 / 0.847 / **0.877** | 0.465 / **0.486** / 0.424 |
  | South America (SMIA) | 0.794 / 0.734 / **0.836** | 0.406 / 0.400 / **0.416** |
  | Sub-Saharan Africa (SMIA) | 0.696 / 0.733 / **0.817** | 0.241 / 0.244 / **0.253** |
  | South Asia (SMIA) | 0.714 / 0.759 / **0.850** | 0.204 / 0.267 / **0.288** |
  | East Asia (SMIA) | 0.793 / 0.817 / **0.836** | 0.398 / **0.413** / 0.375 |
  | Weak regions pooled | 0.729 / 0.778 / **0.843** | 0.350 / **0.361** / 0.353 |

- **Reading:**
  - The location-agnostic features help:
    - The global model is better than the current one in the U.S. and in four of five weak-label regions.
    - The v2 features alone, trained only on U.S. data, transfer to Europe *worse* (within ±1 0.847, Spearman 0.449). The gain therefore needs the multi-continent labels, not just new features.
  - It still loses to the current model in Europe, narrowly: within ±1 −0.012, Spearman −0.005.
  - Outside the U.S., *both* ML models lose to the transparent rule-based blend on within ±1. In most regions they also lose on Spearman.
  - The ML models flag drought far more often than the label systems do. Their D1+ hit rate and false-alarm ratio are both higher than the rules'.
- **Second candidate (added after the first run, so declared as post hoc):** the same model without class balancing, on the hypothesis that balancing to U.S. class frequencies causes the over-prediction.
  - Within ±1 rises everywhere (Europe 0.876, weak regions 0.842).
  - But Spearman and D1+ detection fall sharply (U.S. 0.595 vs. 0.654; U.S. D1+ hit rate 0.43 vs. 0.70).
  - It fails all three checks.
- **Decision:** **not adopted.**
  - The current U.S. model stays, served only in the contiguous U.S. Everywhere else the rule-based blend stays. On within ±1 it beat the current and the global model in every held-out region and was best overall in Europe and on the pooled weak regions (the unbalanced variant edged it only in Australia and Africa, at the cost of Spearman in Australia and of detection everywhere). So this is now evidence-based rather than a default.
  - The serving code is ready for a region-gated global model (`model_regions` in the model metadata), but no such model ships.
- **Caveats:**
  - Re-running the current configuration on today's folds gives 0.879 / 0.654, not EXP-09's 0.889 / 0.679. The folds group counties differently, so differences of about 0.01 in within ±1 are at the level of fold noise.
  - All comparisons above use identical samples and folds.
  - Weak-label results measure agreement with one modelled soil-moisture product, not with expert drought maps.
- **Next:** add expert-curated categorical labels where they exist (e.g. national drought monitors in Mexico/NADM, Canada and South Africa). Try an ordinal or regression target with per-region calibration instead of class balancing.

## EXP-12 Global yield level and year-to-year skill against FAOSTAT (adopted: calendars, antecedent soil water, calibration)
- **Question:** the season model was only checked at a few demo sites. How close are its yields to national statistics worldwide, and can a few transparent factors close the gap without overfitting?
- **Data and method:** see VALIDATION.md V10 and `scripts/yield_benchmark.py`.
  - 263 country × crop pairs in 41 countries and 761 MIRCA2000 cropland sites.
  - Sacks et al. (2010) sowing dates, NASA POWER weather, 2000–2024 seasons.
  - Every calibration is scored **leave-one-country-out**.
- **Step 1: calendars.**
  - The first run used MIRCA2000's condensed calendars, which treat Russia and Kazakhstan as single units listed as Sept→July wheat.
  - The spring-wheat belts of Kurgan and northern Kazakhstan were therefore simulated as winter wheat.
  - Switching to Sacks et al. (2010) cell calendars (MIRCA2000 only as the last fallback) cut the held-out RMSLE of the best structure from 0.578 to 0.512.
  - Russia 2010 moved from rank 21 to rank 1 of 25 seasons.
- **Step 2: antecedent soil water** (model change).
  - **Observation:** before, soil below the sowing root zone entered the root zone at field capacity every season. Deep roots therefore always found a full profile, so winter-rain droughts were missed: with Sacks calendars, Morocco 2007 ranked 9/25 and 2016 11/25.
  - **Change:** `simulate(antecedent_days=180)`, now the default for annual crops. A fallow bucket over the full root zone runs from 180 days before sowing:
    - it starts at 60 % depletion (the previous crop);
    - evaporation is 0.3·ET₀·(1 − D/TAW) (stage-2 drying);
    - rain refills it.
    The resulting depletion sets the initial and deeper soil water.
  - **Result:**

    | | before (FC below roots) | after (180-day antecedent) |
    |---|---|---|
    | Documented droughts in worst 3 / worst 5 of 25 seasons | 11 / 15 | **13 / 17** |
    | Median rank of the 25 documented drought seasons | 4 | **3** |
    | Median detrended r with FAOSTAT | 0.13 | 0.14 |
    | Held-out level RMSLE (adopted calibration) | 0.498 | 0.501 |
    | V5 Ames 2012 / 1988 | 1 / 2 | **1 / 2** |
    | V5 Machakos short rains 2016 / 2005 | 6 / 8 | **4 / 3** |

  - Morocco 2007 and 2016 moved to ranks 3 and 4, and South Africa 2016 to rank 2. One case got worse: eastern Australia 2019 went from rank 1 to 7.
- **Step 3: calibration structure.** Held-out RMSLE of the level (before: 0.843):

  | Structure | Parameters | Held-out RMSLE | within ±30 % |
  |---|---|---|---|
  | crop factor only | 15 | 0.631 | 37 % |
  | crop + Köppen zone | 19 | 0.596 | 41 % |
  | crop + region | 26 | 0.512 | 52 % |
  | crop + region + zone | 30 | 0.518 | 49 % |
  | crop + region + irrigated factor | 27 | 0.500 | 53 % |
  | crop + region + crop×region (ridge) + irrigated | ~140 | 0.488 | 57 % |
  | crop + region × crop sensitivity (+ irrigated) | 41 (42) | 0.495 (0.487) | 52 % (55 %) |
  | **anchored crop + region × crop sensitivity** (adopted) | **38** | **0.501** | **54 %** |
  | anchored, + irrigated factor | 39 | 0.496 | 54 % |

  - Region beats climate zone. Once the region is known, a zone term adds nothing: management, not climate, explains the residual level.
  - The unanchored structures score marginally better on average, but fail where the demo farms are. They put U.S. maize at 6.7–7.3 t/ha (FAOSTAT 10.0) and Spanish maize at 6–7 (10.8): low-input pairs (maize in sub-Saharan Africa at 20 % of the simulated level) pull the shared crop factor down.
  - The anchored structure works in two stages:
    1. crop potential factors are fitted only in the reference regions that `typical_yield_t_ha` was built from;
    2. regional yield gaps, scaled per crop, are fitted on the rest.
  - The global irrigated factor (×1.37) was dropped. It mainly corrected irrigated rice and wheat, and inflated irrigated U.S. maize.
- **Honest caveat:** the candidate list grew after seeing results (irrigated factor, sensitivity, anchoring). Each candidate is still scored on countries its factors never saw, but choosing among nine structures on the same benchmark makes the 0.50 slightly optimistic.
- **Decision:** adopted (ADR-022). Factors are in `config/yield_calibration.yaml` and unit-tested (`tests/test_yieldcal.py`).

## EXP-10 Field boundary detection: superpixel growing vs. field-scale graph segmentation
- **v1:** SLIC superpixels (~1,600) + colour/edge region growing at native resolution. It under-segmented badly: Fallon 1.6 of ~5.5 ha, Machakos one stripe, Córdoba 0.03 ha (the tap was on a hedge).
- **v2 (adopted):**
  - Downsample to ~2.7 m and median-filter, which removes in-field texture.
  - Felzenszwalb segmentation.
  - Snap the seed to the calmest pixel nearby.
  - Edge-aware growth (median border gradient below max(p90, 5)), re-evaluating neighbours as the region grows.
  - Visual check on 4 farms: Fallon and Córdoba correct; Iowa correct except one leak through a farmstead gap; Machakos terraces not merged.
  - Synthetic test with an internal irrigation border: passes.
- **Not adopted:** a stricter border statistic (65th percentile). It still leaked in Iowa and broke the synthetic test.
- **Roadmap:** a promptable segmentation foundation model (e.g. SAM) on the GPU box, as an optional service.

## EXP-13 Field boundary detection worldwide: v2 vs. learned edge map + candidate selection (v3)
- **Hypothesis:** the v2 detector, tuned by eye on four demo fields, does not transfer worldwide. A small edge model trained on open field-boundary labels, plus a learned choice among scale-adaptive candidate regions, raises IoU in countries never used for development.
- **Benchmark (VALIDATION V15):**
  - 467 Fields of The World (FTW) fields in 25 countries, stratified by size. Simulated taps; production code path on Esri World Imagery.
  - DEV countries (AT, FR, IN, NL, ES) were fixed before any tuning. The other 20 countries (314 fields) were scored once at the end.
- **Steps (mean IoU on DEV fields, Esri imagery):**

  | Variant | DEV IoU |
  |---|---|
  | v2 Felzenszwalb + region growing (baseline) | 0.25 |
  | Classical cost map (Lab gradient, 2 scales) + threshold-sweep flood fill + hand-made score | 0.30 |
  | … tuned (median 3, compactness weight 0) | 0.33 |
  | Oracle: best candidate of that sweep | 0.58 |
  | Learned edge map (U-Net, z17 orthophoto windows) + same sweep + hand-made score | 0.51–0.53 |
  | Oracle: best candidate of the learned sweep | 0.70 |
  | + learned selector (GBM on 14 candidate features) | 0.57 |
  | + zoom-16 training windows, cross-fitted selector, final model | 0.58 |
  | + rim-contrast × solidity² prior (w = 0.3), closing r = 2 (**adopted**) | **0.58** |

  - Diagnosis of v2: it leaked through weak borders into neighbouring fields and villages. The median detected area was 6× the true area, and 65× for plots under 0.5 ha.
  - The oracle rows show that, after the sweep, *choosing* the right candidate was the bottleneck. That motivated the learned selector.
- **Selector cross-country check (orthophotos):**
  - Trained on FR+ES, tested on NL+AT: selected IoU 0.64 (oracle 0.74).
  - Trained on NL+AT, tested on FR+ES: 0.59 (oracle 0.70).
  - Most important features: area relative to the median candidate (0.56), solidity (0.14), log area (0.13).
- **Demo-field regression (Ames).**
  - The selector alone cut the 48 ha Ames quarter section into a 21 ha piece: it had seen few > 40 ha fields.
  - Adding 0.3 × rim contrast × solidity² to the predicted IoU fixed Ames (IoU 0.88 → 0.91 vs. the stored rectangle) and was neutral to positive on DEV (0.578 → 0.582).
  - A closing of radius 2 px removed slits along Fallon's irrigation checks.
- **Result on the 20 held-out countries (314 fields):**
  - Mean IoU **0.24 → 0.52** (Δ +0.28, 95 % bootstrap CI +0.25 … +0.32). Every country improved: Brazil least (+0.05, fields up to 150 ha exceed the zoom-16 window), Vietnam most (0.03 → 0.49).
  - IoU ≥ 0.5 rose from 18 % to 53 % of fields; boundary F (5 m) from 0.16 to 0.44.
  - By size: S 0.13 → 0.41, M 0.18 → 0.54, L 0.30 → 0.64, XL 0.37 → 0.49.
  - Africa 0.20 → 0.49, Asia 0.06 → 0.40.
- **Demo fields:**
  - Ames improved and Machakos was unchanged (one terrace strip).
  - Fallon and Córdoba are lower against their stored presets (0.93, 0.79). Those presets *are* v2 outputs, so that comparison is circular.
  - Checked by eye, Fallon is the same field (5.52 vs. 5.53 ha) and v3 fixes v2's cut through the Córdoba field (VALIDATION V15 figure).
- **Speed (CPU):**
  - On the data box, one process with cached tiles: median 0.2 s per tap, 95th percentile 1.0 s (v2: 0.4 s and 1.7 s).
  - On a laptop (Apple silicon, numpy): median 0.5 s per window, max ≈ 2 s. A tap needs two windows only when the field touches the zoom-17 window edge.
  - Model files: 1.0 MB (U-Net) + 58 KB (trees). No new dependency: inference is plain numpy.
- **Not adopted:**
  - Selector alone without the prior (Ames regression).
  - Prior weight 0.5 (hurt 0.5–2 ha fields).
  - Larger closing radius 3 (no gain).
  - Training on Esri imagery. Open orthophotos were used instead, so no question over Esri's terms of use for ML training arises.
- **Decision:** adopted (ADR-026). v2 remains as the automatic fallback when the model files are missing.

## EXP-08 AquaCrop-style biomass vs. FAO-33 yield response (diagnostic)
- The season model reports both: the FAO-33 Ky yield (used in the product) and an AquaCrop-style WP*·Σ(Tr/ET₀) biomass. They are kept side by side for transparency. The FAO-33 approach is used because its parameters exist for every crop in the table, including forage and cover crops, and because it responds directly to the water-stress question farmers ask.
