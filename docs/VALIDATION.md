# Validation

Every FieldShift output that drives advice is compared with an **independent** reference. Tables are generated from `docs/validation/results.json` by `scripts/validation_report.py`, after running `scripts/validate.py` on the data box. The numbers below therefore match the code at the time of the run. Figures (`docs/validation/*.png`) are produced by the same run.

How to read this page:
- Good agreement means the inputs and physics are sound. It does **not** prove the advice is right on a given field: the references are themselves models or coarse data.
- Weak results are kept and explained.

<!-- RESULTS:BEGIN -->
### V1 · Reference ET₀ (FieldShift FAO-56 PM from NASA POWER) vs. ERA5 FAO-56 ET₀, daily 2015–2024
_run: 2026-11-14T18:26:34+00:00_

| Site | n days | daily r | daily RMSE (mm/d) | daily bias (mm/d) | monthly r | monthly bias (mm/mo) |
|---|---|---|---|---|---|---|
| Fallon, NV | 3653 | 0.97 | 0.78 | -0.48 | 0.996 | -14.6 |
| Ames, IA | 3653 | 0.96 | 0.53 | -0.14 | 0.988 | -4.1 |
| Córdoba, ES | 3653 | 0.98 | 0.49 | 0.01 | 0.997 | 0.3 |
| Machakos, KE | 3653 | 0.86 | 0.77 | 0.56 | 0.905 | 16.9 |

### V2 · Rain-fed root-zone water (1 − Dr/TAW) vs. ERA5-Land 7–100 cm soil moisture
_run: 2026-11-14T18:26:35+00:00_

| Site | crop | seasons | median r per season | pooled standardized r |
|---|---|---|---|---|
| Ames, IA | maize | 9 | 0.71 | 0.58 |
| Córdoba, ES | winter_wheat | 9 | 0.73 | 0.72 |
| Machakos, KE | maize | 9 | 0.49 | 0.30 |

### V3 · Rain-fed root-zone water vs. NASA SMAP L4 root-zone soil moisture (0–100 cm)
_Pending at v1.0.0: the NASA AppEEARS point-extraction requests for this check (submitted 14 Nov 2026) were still queued or processing at NASA when the release was cut. `scripts/appeears_smap.py` and `scripts/validate.py` reproduce it once they finish. No result is claimed until then._

### V4 · Drought status vs. U.S. Drought Monitor (weekly 2005–2024, county DSCI)
_run: 2026-11-14T18:28:15+00:00_

| County | weeks | ρ SPI-90 | ρ SPEI-90 | ρ SPEI-12 | ρ status v1 | ρ status v2 (used) | D1 hit rate v2 | D1 false-alarm ratio v2 |
|---|---|---|---|---|---|---|---|---|
| Fallon, NV | 1045 | 0.14 | 0.29 | 0.67 | 0.22 | 0.38 | 0.42 | 0.25 |
| Ames, IA | 1045 | 0.63 | 0.70 | 0.65 | 0.66 | 0.74 | 0.68 | 0.37 |

### V5 · Documented drought years in simulated rain-fed yields
_run: 2026-11-14T18:28:15+00:00_

| Site / season | years simulated | documented drought year | rank (1 = worst) |
|---|---|---|---|
| Ames, IA maize | 40 | 2012 | **1** |
| Ames, IA maize | 40 | 1988 | **2** |
| Machakos, KE maize (short rains) | 34 | 2016 | **6** |
| Machakos, KE maize (short rains) | 34 | 2005 | **8** |

### V6 · Irrigated alfalfa ET at the Fallon field: model vs NASA ECOSTRESS (70 m) and MODIS MOD16 (500 m)
_run: 2026-11-14T15:44:56+00:00_

_Pending at v1.0.0: the NASA AppEEARS point-extraction requests for this check (submitted 14 Nov 2026) were still queued or processing at NASA when the release was cut. `scripts/appeears_smap.py` and `scripts/validate.py` reproduce it once they finish. No result is claimed until then._

### V7 · Late-blight weather risk (Hutton criteria, NASA POWER hourly), Ithaca NY, Jun–Aug
_run: 2026-11-14T18:28:15+00:00_

| Year | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Hutton days | 42 | 60 | 34 | 62 | 57 | 33 | 47 | 25 | 57 | 49 | 45 |

2009 (documented epidemic) ranks **3 of 11**.

### V8 · AI drought classifier on sites, regions and climate zones the model never saw
_trained: 2026-11-14T23:48:40+00:00 · 310 sites in 7 regions · 229,040 labels · U.S.: GroupKFold(5) by county; other regions: leave-one-region-out; zones: leave-one-climate-zone-out_

**U.S., native USDM scale (None…D4), counties held out (GroupKFold 5); Spearman vs. DSCI**

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 83,600 | 0.592 | 0.879 | 0.569 | 0.654 | 0.703 | 0.411 |
| Global model (v2 features, class-balanced) | 83,600 | 0.635 | 0.894 | 0.503 | 0.687 | 0.647 | 0.388 |
| Global model (v2 features, unbalanced) | 83,600 | 0.667 | 0.878 | 0.502 | 0.595 | 0.431 | 0.243 |
| Rule-based blend | 83,600 | 0.590 | 0.862 | 0.595 | 0.548 | 0.449 | 0.423 |

**Per region, harmonised scale (None / D0·Watch / D1·Warning / D2+·Alert).** U.S. = county CV; every other region = leave-one-region-out (the global model never saw that region; the current model never saw anything outside the U.S.). Spearman vs. the label level.

_U.S. (USDM): 80 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 83,600 | 0.625 | 0.898 | 0.501 | 0.625 | 0.703 | 0.411 |
| Global model (v2 features, class-balanced) | 83,600 | 0.658 | 0.911 | 0.446 | 0.663 | 0.647 | 0.388 |
| Global model (v2 features, unbalanced) | 83,600 | 0.679 | 0.896 | 0.454 | 0.592 | 0.431 | 0.243 |
| Rule-based blend | 83,600 | 0.604 | 0.879 | 0.539 | 0.533 | 0.449 | 0.423 |
| v2 features, trained on Europe only | 83,600 | 0.592 | 0.864 | 0.571 | 0.510 | 0.576 | 0.507 |

_Europe (EDO CDI): 80 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 37,440 | 0.576 | 0.859 | 0.604 | 0.493 | 0.594 | 0.514 |
| Global model (v2 features, class-balanced) | 37,440 | 0.581 | 0.847 | 0.619 | 0.488 | 0.592 | 0.539 |
| Global model (v2 features, unbalanced) | 37,440 | 0.667 | 0.876 | 0.479 | 0.490 | 0.433 | 0.439 |
| Rule-based blend | 37,440 | 0.590 | 0.887 | 0.533 | 0.526 | 0.447 | 0.499 |
| v2 features, trained on U.S. only | 37,440 | 0.535 | 0.847 | 0.665 | 0.449 | 0.550 | 0.558 |

_Australia (GDO SMIA, weak): 30 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 21,600 | 0.337 | 0.647 | 1.122 | 0.465 | 0.823 | 0.738 |
| Global model (v2 features, class-balanced) | 21,600 | 0.522 | 0.847 | 0.681 | 0.486 | 0.616 | 0.641 |
| Global model (v2 features, unbalanced) | 21,600 | 0.569 | 0.885 | 0.570 | 0.438 | 0.396 | 0.586 |
| Rule-based blend | 21,600 | 0.524 | 0.877 | 0.614 | 0.424 | 0.409 | 0.580 |
| v2 features, trained on U.S. only | 21,600 | 0.404 | 0.706 | 0.961 | 0.497 | 0.817 | 0.719 |

_South America (GDO SMIA, weak): 30 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 21,600 | 0.514 | 0.794 | 0.763 | 0.406 | 0.547 | 0.578 |
| Global model (v2 features, class-balanced) | 21,600 | 0.519 | 0.734 | 0.897 | 0.400 | 0.682 | 0.610 |
| Global model (v2 features, unbalanced) | 21,600 | 0.638 | 0.834 | 0.603 | 0.372 | 0.282 | 0.366 |
| Rule-based blend | 21,600 | 0.550 | 0.836 | 0.661 | 0.416 | 0.472 | 0.502 |
| v2 features, trained on U.S. only | 21,600 | 0.558 | 0.790 | 0.723 | 0.404 | 0.567 | 0.572 |

_Sub-Saharan Africa (GDO SMIA, weak): 30 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 21,600 | 0.394 | 0.696 | 1.029 | 0.241 | 0.494 | 0.725 |
| Global model (v2 features, class-balanced) | 21,600 | 0.464 | 0.733 | 0.950 | 0.244 | 0.528 | 0.707 |
| Global model (v2 features, unbalanced) | 21,600 | 0.601 | 0.831 | 0.642 | 0.299 | 0.248 | 0.612 |
| Rule-based blend | 21,600 | 0.519 | 0.817 | 0.730 | 0.253 | 0.299 | 0.639 |
| v2 features, trained on U.S. only | 21,600 | 0.449 | 0.697 | 0.963 | 0.277 | 0.520 | 0.718 |

_South Asia (GDO SMIA, weak): 30 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 21,600 | 0.402 | 0.714 | 0.996 | 0.204 | 0.482 | 0.763 |
| Global model (v2 features, class-balanced) | 21,600 | 0.467 | 0.759 | 0.896 | 0.267 | 0.532 | 0.704 |
| Global model (v2 features, unbalanced) | 21,600 | 0.594 | 0.841 | 0.635 | 0.170 | 0.133 | 0.668 |
| Rule-based blend | 21,600 | 0.557 | 0.850 | 0.633 | 0.288 | 0.287 | 0.629 |
| v2 features, trained on U.S. only | 21,600 | 0.457 | 0.697 | 0.965 | 0.232 | 0.548 | 0.757 |

_East Asia (GDO SMIA, weak): 30 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 21,600 | 0.497 | 0.793 | 0.778 | 0.398 | 0.527 | 0.624 |
| Global model (v2 features, class-balanced) | 21,600 | 0.540 | 0.817 | 0.710 | 0.413 | 0.503 | 0.564 |
| Global model (v2 features, unbalanced) | 21,600 | 0.614 | 0.821 | 0.638 | 0.326 | 0.274 | 0.490 |
| Rule-based blend | 21,600 | 0.558 | 0.836 | 0.650 | 0.375 | 0.341 | 0.531 |
| v2 features, trained on U.S. only | 21,600 | 0.521 | 0.754 | 0.816 | 0.415 | 0.648 | 0.625 |

_All weak-label regions pooled: 150 sites_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 108,000 | 0.429 | 0.729 | 0.938 | 0.350 | 0.572 | 0.697 |
| Global model (v2 features, class-balanced) | 108,000 | 0.502 | 0.778 | 0.827 | 0.361 | 0.574 | 0.649 |
| Global model (v2 features, unbalanced) | 108,000 | 0.603 | 0.842 | 0.618 | 0.329 | 0.269 | 0.545 |
| Rule-based blend | 108,000 | 0.542 | 0.843 | 0.658 | 0.353 | 0.365 | 0.571 |

**Leave-one-climate-zone-out (harmonised scale)**

_arid: 87 sites (US 13, EU 11, AUS 26, SAM 3, AFR 14, SAS 12, EAS 8)_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 64,093 | 0.352 | 0.684 | 1.077 | 0.438 | 0.820 | 0.629 |
| Global model (v2 features, class-balanced) — zone held out | 64,093 | 0.414 | 0.749 | 0.923 | 0.436 | 0.732 | 0.576 |
| Global model (v2 features, unbalanced) — zone held out | 64,093 | 0.502 | 0.801 | 0.752 | 0.436 | 0.575 | 0.513 |
| Rule-based blend | 64,093 | 0.505 | 0.837 | 0.693 | 0.411 | 0.357 | 0.456 |

_tropical: 42 sites (AUS 3, SAM 18, AFR 15, SAS 6)_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 30,240 | 0.498 | 0.777 | 0.807 | 0.238 | 0.380 | 0.675 |
| Global model (v2 features, class-balanced) — zone held out | 30,240 | 0.476 | 0.694 | 1.020 | 0.279 | 0.590 | 0.694 |
| Global model (v2 features, unbalanced) — zone held out | 30,240 | 0.627 | 0.819 | 0.636 | 0.272 | 0.235 | 0.575 |
| Rule-based blend | 30,240 | 0.535 | 0.805 | 0.729 | 0.267 | 0.336 | 0.643 |

_temperate: 79 sites (US 28, EU 21, AUS 1, SAM 9, AFR 1, SAS 9, EAS 10)_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 60,688 | 0.611 | 0.883 | 0.533 | 0.532 | 0.546 | 0.442 |
| Global model (v2 features, class-balanced) — zone held out | 60,688 | 0.648 | 0.859 | 0.541 | 0.524 | 0.512 | 0.468 |
| Global model (v2 features, unbalanced) — zone held out | 60,688 | 0.670 | 0.846 | 0.539 | 0.392 | 0.225 | 0.304 |
| Rule-based blend | 60,688 | 0.610 | 0.888 | 0.524 | 0.536 | 0.483 | 0.424 |

_cold: 102 sites (US 39, EU 48, SAS 3, EAS 12)_

| Model | n | Exact | Within ±1 | MAE | Spearman | D1+ hit | D1+ FAR |
|---|---|---|---|---|---|---|---|
| Current model (U.S.-trained, v1 features) | 74,019 | 0.613 | 0.879 | 0.539 | 0.490 | 0.560 | 0.561 |
| Global model (v2 features, class-balanced) — zone held out | 74,019 | 0.658 | 0.849 | 0.508 | 0.483 | 0.678 | 0.622 |
| Global model (v2 features, unbalanced) — zone held out | 74,019 | 0.718 | 0.885 | 0.423 | 0.436 | 0.385 | 0.481 |
| Rule-based blend | 74,019 | 0.616 | 0.890 | 0.511 | 0.492 | 0.447 | 0.557 |

**Weak-label quality.** SMIA thresholds (D0…D4, calibrated on U.S. sites): [-0.235, -0.762, -1.208, -1.732, -2.465]. Agreement of the SMIA label with USDM (U.S.): within ±1 0.844, Spearman 0.488; with CDI (Europe): within ±1 0.892, Spearman 0.540.

- Global model (v2 features, class-balanced): us_at_least_current: True, eu_better_than_current: False, weak_better_than_current: True
- Global model (v2 features, unbalanced): us_at_least_current: False, eu_better_than_current: False, weak_better_than_current: False

**Adopted: False** (served: Current model (U.S.-trained, v1 features)). Model used in: US; elsewhere the rule-based blend.

<!-- RESULTS:END -->

## V-IMERG · Rain: NASA POWER vs. GPM IMERG vs. their blend, against 18 rain gauges on 6 continents (2001–2025)
_run: 2026-11-15 · `scripts/validate_imerg.py` → `docs/validation/imerg.json`_

**Question.** Does GPM IMERG rain, or a POWER/IMERG blend, describe rain at the field better than the NASA POWER (MERRA-2) rain FieldShift used so far? Adopt it only where it helps.

**Design.**
- Reference: GHCN-Daily station precipitation (NOAA NCEI), QC-flagged values dropped. 18 stations: the four demo regions (Fallon, Ames, Córdoba, Nairobi for Machakos), plus Jaén, West Africa (Niamey, Ouagadougou, Bamako, Dakar), India (Delhi, Pune, Hyderabad, Nagpur), Bangkok, Darwin, Wagga Wagga, San Juan and Bogotá. 12 are tropical (|lat| ≤ 23.5°).
- Products extracted at each station from the anonymous NASA POWER point API: POWER `PRECTOTCORR` (as served, local solar time) and IMERG Final `IMERG_PRECTOT` (UTC days).
- Only days with a gauge value count. One common lag (−1/0/+1 day) per station is chosen on the mean of POWER and IMERG, so neither is favoured (many gauges report the 24 h ending in the morning).
- Metrics: daily Pearson r; wet-day critical success index (≥ 1 mm); monthly totals over the same gauge days (months with ≥ 20 gauge days): r, bias, Kling–Gupta efficiency (KGE); r of 3-month anomalies (an SPI-3 proxy, what the drought indicators see).
- The blend weight (0.5) was fixed before the run; 0.3 and 0.7 and three alternative designs are reported for sensitivity.

**Per station (POWER → adopted blend):**

| Site (GHCN station) | Continent | Zone | gauge months | daily r POWER → blend | monthly KGE POWER → blend | 3-month anomaly r POWER → blend | monthly bias POWER / IMERG / blend |
|---|---|---|---|---|---|---|---|
| Fallon Exp. Stn, Nevada (demo field) (USC00262780) | North America | extratropics | 273 | 0.62 → **0.66** | 0.35 → **0.63** | 0.80 → **0.86** | +51 % / +13 % / +32 % |
| Ames 8 WSW, Iowa (demo field) (USC00130200) | North America | extratropics | 300 | 0.59 → **0.73** | 0.81 → **0.87** | 0.89 → **0.89** | -7 % / +9 % / +1 % |
| Córdoba airport, Spain (demo field) (SP000008410) | Europe | extratropics | 300 | 0.83 → **0.81** | 0.74 → **0.83** | 0.97 → **0.96** | -16 % / -0 % / -8 % |
| Jaén, Spain (SPE00120170) | Europe | extratropics | 300 | 0.77 → **0.77** | 0.71 → **0.83** | 0.94 → **0.94** | -16 % / +3 % / -6 % |
| Nairobi JKIA, Kenya (Machakos demo) (KE000063740) | Africa | tropics | 41 | 0.25 → **0.34** | 0.44 → **0.67** | 0.82 → **0.85** | -36 % / +1 % / -18 % |
| Niamey, Niger (NG000001052) | Africa | tropics | 52 | 0.32 → **0.48** | 0.93 → **0.96** | 0.98 → **0.99** | +4 % / +3 % / +4 % |
| Ouagadougou, Burkina Faso (UVM00065503) | Africa | tropics | 59 | 0.26 → **0.39** | 0.88 → **0.91** | 0.96 → **0.97** | +1 % / +4 % / +2 % |
| Bamako-Sénou, Mali (MLM00061291) | Africa | tropics | 38 | 0.20 → **0.34** | 0.73 → **0.88** | 0.87 → **0.93** | +5 % / +3 % / +4 % |
| Dakar-Yoff, Senegal (SG000061641) | Africa | tropics | 49 | 0.36 → **0.49** | 0.70 → **0.71** | 0.94 → **0.96** | -2 % / -5 % / -4 % |
| New Delhi Safdarjung, India (IN022021900) | Asia | extratropics | 53 | 0.65 → **0.68** | 0.78 → **0.72** | 0.97 → **0.98** | -8 % / -13 % / -11 % |
| Pune, India (IN012190100) | Asia | tropics | 100 | 0.67 → **0.71** | -0.90 → **-0.38** | 0.92 → **0.92** | +137 % / +64 % / +100 % |
| Hyderabad Begumpet, India (IN001080500) | Asia | tropics | 88 | 0.75 → **0.75** | 0.90 → **0.93** | 0.96 → **0.97** | -2 % / +10 % / +4 % |
| Nagpur Sonegaon, India (IN012141800) | Asia | tropics | 66 | 0.65 → **0.67** | 0.85 → **0.93** | 0.98 → **0.98** | -9 % / +9 % / +0 % |
| Bangkok Don Muang, Thailand (TH000048456) | Asia | tropics | 156 | 0.56 → **0.56** | 0.68 → **0.70** | 0.81 → **0.84** | -11 % / -8 % / -10 % |
| Darwin airport, Australia (ASN00014015) | Australia | tropics | 300 | 0.67 → **0.79** | 0.84 → **0.89** | 0.76 → **0.87** | -7 % / -1 % / -4 % |
| Wagga Wagga, Australia (ASN00072150) | Australia | extratropics | 292 | 0.70 → **0.84** | 0.86 → **0.88** | 0.93 → **0.95** | +5 % / +11 % / +8 % |
| San Juan, Puerto Rico (RQW00011641) | North America | tropics | 300 | 0.44 → **0.58** | 0.48 → **0.69** | 0.52 → **0.70** | -25 % / -6 % / -16 % |
| Bogotá El Dorado, Colombia (CO000080222) | South America | tropics | 133 | 0.38 → **0.34** | 0.07 → **0.03** | 0.66 → **0.69** | +84 % / +98 % / +91 % |

**By zone:**

| Zone (sites) | Product | daily r | wet-day CSI | monthly r | monthly KGE | 3-month anomaly r | mean abs. bias | beats POWER (daily r / KGE / anomaly r) |
|---|---|---|---|---|---|---|---|---|
| tropics (12) | POWER (served before) | 0.459 | 0.518 | 0.818 | 0.551 | 0.849 | 26.9 % | — |
| tropics (12) | IMERG alone | 0.479 | 0.504 | 0.863 | 0.698 | 0.890 | 17.7 % | 7/12 / 10/12 / 8/12 |
| tropics (12) | **Blend 50/50 (adopted)** | 0.537 | 0.523 | 0.865 | 0.660 | 0.889 | 21.3 % | 11/12 / 11/12 / 11/12 |
| tropics (12) | POWER rescaled monthly to IMERG | 0.477 | 0.517 | 0.864 | 0.697 | 0.889 | 17.7 % | 10/12 / 11/12 / 8/12 |
| tropics (12) | Bridge: POWER × (0.5 + 0.5·ratio) | 0.460 | 0.518 | 0.823 | 0.619 | 0.852 | 22.6 % | 7/12 / 8/12 / 6/12 |
| tropics (12) | Blend 30 % IMERG | 0.529 | 0.523 | 0.852 | 0.622 | 0.878 | 23.5 % | 12/12 / 11/12 / 11/12 |
| tropics (12) | Blend 70 % IMERG | 0.521 | 0.526 | 0.870 | 0.687 | 0.894 | 19.8 % | 8/12 / 11/12 / 10/12 |
| tropics (12) | Blend, rescaled to IMERG monthly | 0.534 | 0.523 | 0.867 | 0.700 | 0.891 | 17.5 % | 11/12 / 11/12 / 9/12 |
| extratropics (6) | POWER (served before) | 0.693 | 0.531 | 0.916 | 0.709 | 0.918 | 17.0 % | — |
| extratropics (6) | IMERG alone | 0.676 | 0.512 | 0.913 | 0.837 | 0.920 | 8.3 % | 2/6 / 4/6 / 3/6 |
| extratropics (6) | **Blend 50/50 (adopted)** | 0.749 | 0.554 | 0.929 | 0.793 | 0.931 | 11.0 % | 5/6 / 5/6 / 4/6 |
| extratropics (6) | POWER rescaled monthly to IMERG | 0.685 | 0.526 | 0.910 | 0.825 | 0.921 | 9.1 % | 1/6 / 4/6 / 3/6 |
| extratropics (6) | Bridge: POWER × (0.5 + 0.5·ratio) | 0.693 | 0.529 | 0.918 | 0.780 | 0.920 | 11.5 % | 1/6 / 4/6 / 3/6 |
| extratropics (6) | Blend 30 % IMERG | 0.745 | 0.553 | 0.927 | 0.762 | 0.928 | 13.2 % | 5/6 / 5/6 / 4/6 |
| extratropics (6) | Blend 70 % IMERG | 0.731 | 0.546 | 0.927 | 0.818 | 0.930 | 9.5 % | 4/6 / 5/6 / 3/6 |
| extratropics (6) | Blend, rescaled to IMERG monthly | 0.738 | 0.547 | 0.913 | 0.831 | 0.921 | 8.7 % | 4/6 / 4/6 / 3/6 |
| all (18) | POWER (served before) | 0.537 | 0.522 | 0.851 | 0.604 | 0.872 | 23.6 % | — |
| all (18) | IMERG alone | 0.545 | 0.507 | 0.880 | 0.744 | 0.900 | 14.6 % | 9/18 / 14/18 / 11/18 |
| all (18) | **Blend 50/50 (adopted)** | 0.608 | 0.534 | 0.886 | 0.705 | 0.903 | 17.9 % | 16/18 / 16/18 / 15/18 |
| all (18) | POWER rescaled monthly to IMERG | 0.546 | 0.520 | 0.879 | 0.740 | 0.900 | 14.8 % | 11/18 / 15/18 / 11/18 |
| all (18) | Bridge: POWER × (0.5 + 0.5·ratio) | 0.538 | 0.521 | 0.855 | 0.673 | 0.875 | 18.9 % | 8/18 / 12/18 / 9/18 |
| all (18) | Blend 30 % IMERG | 0.601 | 0.533 | 0.877 | 0.669 | 0.895 | 20.1 % | 17/18 / 16/18 / 15/18 |
| all (18) | Blend 70 % IMERG | 0.591 | 0.533 | 0.889 | 0.730 | 0.906 | 16.4 % | 12/18 / 16/18 / 13/18 |
| all (18) | Blend, rescaled to IMERG monthly | 0.602 | 0.531 | 0.882 | 0.744 | 0.901 | 14.5 % | 15/18 / 15/18 / 12/18 |

**Decision (ADR-021).** The 50/50 daily blend beat POWER alone on daily correlation at **16/18** stations (mean r 0.537 → 0.608), on monthly KGE at **16/18** (0.604 → 0.705) and on 3-month anomaly correlation at **15/18** (0.872 → 0.903), and reduced the mean absolute bias from 23.6 % to 17.9 %. It helped in the tropics (11/12 on each of daily r, KGE, anomaly r) and outside them (5/6 on daily r and KGE). It is therefore adopted in both zones, but only inside the validated band |lat| ≤ 45°. IMERG alone has the best monthly amounts (KGE 0.744) but loses on daily timing at half the stations, and the water balance needs daily timing. For IMERG's ~2-month latency the bridge POWER × (0.5 + 0.5·ratio) improves amounts (KGE better at 12/18) without changing timing.

**Where it did not help.** Bogotá (tropical Andes, 2,550 m): both products overestimate by ~+90 % and the blend is no better. Delhi: KGE fell slightly (0.78 → 0.72) because IMERG is drier there; daily r still rose. Pune (lee side of the Western Ghats): POWER +137 %, IMERG +64 %; the blend halves the error but is still poor (LIMITATIONS).

**Caveat.** IMERG Final is calibrated to GPCC monthly gauge analyses and MERRA-2's corrected rain to CPC gauges; GHCN stations feed both, so this is not a fully independent test, and the monthly scores flatter both products more than the daily ones. Tropical GHCN records are patchy (38–156 usable months at 10 of the 12 tropical stations).

## V-GRACE · Regional water storage (GRACE/GRACE-FO) vs. USGS groundwater wells and published GRACE trends
_run: 2026-11-15 · `scripts/validate_grace.py` → `docs/validation/grace.json`_

**Question.** Does FieldShift's water-storage indicator (JPL RL06.3 mascons at the field's cell, harmonic trend model with AR(1)-adjusted significance) move with groundwater where wells exist, and does it reproduce published GRACE trends elsewhere?

**Design.**
- Wells: USGS groundwater-level field measurements (parameter 72019, depth to water), anonymous USGS Water Data OGC API, in a 2° × 2° box (≈ one mascon) around 12 U.S. aquifer regions incl. the Fallon and Ames demo fields. Wells with ≥ 12 years of data in 2003–2025 are kept; the regional index is the median of annual water-level anomalies across wells (≥ 5 wells per year).
- Wells measure hydraulic head (m) and GRACE measures mass (cm of water); without the aquifer's specific yield only co-variation and trend direction are comparable, not magnitude.
- Metrics: r of annual means; agreement of trend sign; agreement of FieldShift's class (declining/likely/stable/rising) with the wells' trend class (OLS on the annual index, same p-value thresholds).

| Region | USGS wells (≥ 12 yrs) | years | r (annual) | well level trend (head) | FieldShift GRACE storage trend | agrees: sign / class |
|---|---|---|---|---|---|---|
| Fallon / Carson Desert, NV (demo field) | 257 | 21 | +0.56 | +0.00 m/yr (stable, p = 0.844) | -0.38 cm/yr (declining, p = 0.015) | no / no |
| Ames, IA (demo field) | 3 | 0 | — | too few long well records | — | — |
| Tulare Basin, Central Valley, CA | 35 | 16 | +0.86 | -0.52 m/yr (declining, p = 0.001) | -1.22 cm/yr (likely declining, p = 0.074) | yes / yes |
| Southern High Plains (Ogallala), TX | 382 | 13 | +0.90 | -0.22 m/yr (declining, p = 0.000) | -1.90 cm/yr (declining, p = 0.000) | yes / yes |
| Central High Plains (Ogallala), KS | 345 | 14 | +0.87 | -0.42 m/yr (declining, p = 0.000) | -2.16 cm/yr (declining, p = 0.004) | yes / yes |
| Platte valley / northern High Plains, NE | 1296 | 21 | +0.52 | +0.00 m/yr (stable, p = 0.947) | +0.39 cm/yr (stable, p = 0.319) | yes / yes |
| Mississippi Embayment (Delta), AR | 653 | 21 | +0.23 | -0.02 m/yr (declining, p = 0.056) | +0.09 cm/yr (stable, p = 0.541) | no / no |
| Phoenix basins, AZ | 17 | 16 | +0.23 | -0.04 m/yr (declining, p = 0.129) | -0.43 cm/yr (declining, p = 0.018) | yes / yes |
| Eastern Snake River Plain, ID | 62 | 21 | +0.35 | -0.04 m/yr (declining, p = 0.076) | -0.36 cm/yr (likely declining, p = 0.089) | yes / yes |
| Columbia Plateau, WA | 52 | 21 | +0.56 | -0.04 m/yr (declining, p = 0.044) | -0.49 cm/yr (declining, p = 0.000) | yes / yes |
| Central Florida (Floridan aquifer) | 64 | 21 | +0.75 | +0.01 m/yr (stable, p = 0.604) | +0.76 cm/yr (rising, p = 0.002) | yes / no |
| Long Island, NY | 628 | 21 | +0.07 | -0.01 m/yr (declining, p = 0.164) | +0.29 cm/yr (stable, p = 0.000) | no / no |

**Summary.** GRACE's annual storage co-varied positively with the regional well index in **11/11** usable regions (median r = **0.56**; 0.86–0.90 in the Central Valley and the Ogallala). The trend direction agreed in **8/11** and the FieldShift class in **7/11**. The declining Ogallala, Central Valley, Snake River Plain, Columbia Plateau and Phoenix basins are all called declining or likely declining. Ames had too few long well records in the USGS database.

**Disagreements, and what we changed because of them.**
- **Fallon (demo field):** 257 wells are flat on median while GRACE's region is falling (−0.38 cm/yr, p = 0.015). The shallow aquifer under the Newlands Project is recharged by flood irrigation and canal seepage, while the ~300 km mascon also sees the drying Great Basin (soil, snow, lakes). We therefore renamed the card from "groundwater falling" to **"regional water reserves falling"**, added "check your well", and state the Fallon disagreement in every GRACE Why.
- **Mississippi Embayment, Long Island:** wells decline slightly, GRACE is flat or rising — the wet humid-climate signal (soil and surface water) dominates the mascon. Central Florida: GRACE rising, wells flat.

**Literature check outside the U.S.** (same period as each study, sign and order of magnitude only — the studies used other solutions and corrections):

| Region | Published GRACE trend | Period | FieldShift, same period | FieldShift, 2002–2026 | Reference |
|---|---|---|---|---|---|
| NW India (Punjab, Haryana, Rajasthan) | -4.0 cm/yr | 2002–2008 | -6.57 cm/yr | -5.48 cm/yr (declining) | Rodell et al. 2009, Nature |
| North China Plain | -2.2 cm/yr | 2003–2010 | -2.81 cm/yr | -1.39 cm/yr (likely declining) | Feng et al. 2013, WRR (groundwater) |
| Tigris–Euphrates–western Iran | -2.7 cm/yr | 2003–2009 | -1.86 cm/yr | -0.55 cm/yr (stable) | Voss et al. 2013, WRR |
| Northern Saudi Arabia aquifers | -0.9 cm/yr | 2002–2016 | -0.50 cm/yr | -0.44 cm/yr (declining) | Rodell et al. 2018, Nature |
| Niger / central Sahel | +1.0 cm/yr | 2002–2016 | +0.76 cm/yr | +1.32 cm/yr (rising) | Rodell et al. 2018, Nature (wetting) |
| California Central Valley | -2.0 cm/yr | 2003–2010 | -1.87 cm/yr | -1.22 cm/yr (likely declining) | Famiglietti et al. 2011, GRL |
{"regions_usable": 11, "median_r_annual": 0.56, "r_positive": "11/11", "trend_sign_agrees": "8/11", "class_agrees": "7/11", "literature_sign_agrees": "6/6"}


Sign agrees **6/6**; magnitudes are within a factor of ~2 of the published values (CRI mascons with JPL scale factors are expected to differ from the spherical-harmonic and GLDAS-corrected numbers of the older studies).

## Interpretation

### Where the models are strong
- **Rain (V-IMERG).** Blending NASA POWER with GPM IMERG improved daily correlation with gauges at 16 of 18 stations on 6 continents, with the largest gains (+0.12 to +0.16) at Niamey, Bamako, Ouagadougou, Dakar, San Juan, Darwin, Ames and Wagga Wagga.
- **Regional water storage (V-GRACE).** GRACE storage moved with groundwater levels in 11/11 U.S. aquifer regions and reproduced the sign of 6/6 published depletion or wetting trends.
- **ET₀ (V1).**
  - At the temperate sites, ET₀ from NASA POWER agrees with ERA5 at daily r ≈ 0.97–0.98 and monthly r ≈ 0.99–1.00.
  - The water-balance driver is therefore robust.
  - At Fallon, POWER's ET₀ is ~11 % lower than ERA5's. The two grids mix desert and irrigated valley differently, and the true field value is unknown. Irrigation amounts carry this uncertainty, which is why the cards say "~50 km grid".
- **Drought years (V5).** The season model, driven only by NASA POWER weather, ranks the documented Iowa droughts of **2012 and 1988** at the very bottom of 40 seasons.
- **Drought status (V4), Iowa.** In the rain-fed Corn Belt, the blended status tracks the U.S. Drought Monitor closely (ρ ≈ 0.74).

### Where they are weak, and why
- **Drought in Nevada (V4).**
  - Agreement with the USDM is only moderate.
  - Farm drought in the Lahontan Valley is a **water-supply** drought: Sierra snowpack and Lahontan Reservoir deliveries. Local rain cannot capture that.
  - Adding a 12-month SPEI helped (EXP-03).
  - The proper fix is snowpack and reservoir data plus GRACE-FO storage (ROADMAP #1–2). GRACE storage is now shown as regional context (V-GRACE), but it does not set the drought level.
- **East Africa soil water (V2/V3).**
  - Correlations in Machakos are lower. The causes: bimodal short rains, 50 km rain grids missing convective storms, and known reanalysis biases.
  - Advice there carries lower confidence. Local rain-gauge input would help most.
- **Late blight (V7).**
  - 2009 is among the higher-risk seasons on POWER's grid, but not the top.
  - Hutton criteria were designed for station humidity. The 2009 epidemic was also driven by infected transplants, which weather cannot see.
  - The card therefore says "weather favourable for infection — scout", never "disease present".
- **MOD16 (V6).**
  - MOD16 has no irrigation input and is known to underestimate ET over irrigated fields in arid regions.
  - A large gap to the model is *expected* there. It is shown for transparency, not as a calibration target.

- **AI drought classifier outside the U.S. (V8, EXP-11).**
  - A global model (EDO CDI + GDO soil-moisture labels, location-agnostic features) beats the current U.S. model on held-out U.S. counties and on most held-out weak-label regions. On held-out Europe it falls narrowly behind.
  - Outside the U.S. the rule-based blend beats both the current and the global model on within ±1 in every region. The ML models over-predict drought there: high hit rates, high false-alarm ratios.
  - The ML classifier therefore stays U.S.-only, and the rules serve the rest of the world.
  - The weak SMIA labels agree with USDM and CDI only moderately (Spearman 0.49 / 0.54), so those regional numbers are indicative.

### What was not validated (and why)
- The GRACE indicator outside the U.S. against wells: open long well records were not found in time for India, the Sahel or Spain; only published GRACE trends were compared (V-GRACE).
- IMERG above 45° latitude (snow) and in mountains beyond Bogotá: the blend is switched off poleward of 45°.
- Field-level irrigation timing: this needs farm irrigation logs.
- Absolute yields against county statistics: the NASS API needs a key (ROADMAP #4).
- Rotation scores against field trials: no open dataset fits.

See also [`EXPERIMENTS.md`](EXPERIMENTS.md) for the experiments that changed the code, and [`LIMITATIONS.md`](LIMITATIONS.md).
