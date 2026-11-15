# Validation

Every IA output that drives advice is compared with an **independent** reference. Tables are generated from `docs/validation/results.json` by `scripts/validation_report.py`, after running `scripts/validate.py` on the data box. The numbers below therefore match the code at the time of the run. Figures (`docs/validation/*.png`) are produced by the same run.

How to read this page:
- Good agreement means the inputs and physics are sound. It does **not** prove the advice is right on a given field: the references are themselves models or coarse data.
- Weak results are kept and explained.

<!-- RESULTS:BEGIN -->
### V1 · Reference ET₀ (IA FAO-56 PM from NASA POWER) vs. ERA5 FAO-56 ET₀, daily 2015–2024
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
_run: 2026-11-15T00:33:32+00:00_

| Site / season | years simulated | documented drought year | rank (1 = worst) |
|---|---|---|---|
| Ames, IA maize | 40 | 2012 | **1** |
| Ames, IA maize | 40 | 1988 | **2** |
| Machakos, KE maize (short rains) | 34 | 2016 | **4** |
| Machakos, KE maize (short rains) | 34 | 2005 | **3** |

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

<a id="v9"></a>
### V9 · Rainy-season onset, false starts and season length vs. published onset climatologies (31 sites, 3 continents)
_Generated by `scripts/validate_onset.py` (results in `docs/validation/onset_results.json`). It is kept outside the auto-generated block above, so `validation_report.py` does not overwrite it._

The detector settings are the production defaults in `config/onset.yaml`: Sivakumar (1988) onset and a 100 mm water-balance cessation. They were fixed before the references were collected. Every reference was read in the original source; see `REFS` in the script.

**Summary (error = IA − reference, in days)**

| Reference | Sites | What is compared | Error |
|---|---|---|---|
| IMD new normal onset dates, Pai et al. 2020 | 9 Indian cities | median onset 1984–2025 vs. normal 1961–2019 | bias −1.3, **MAE 3.6**, r = 0.92 |
| Omoyo et al. 2015, Machakos station 1979–2009 | Machakos, Kenya: OND short rains | mean onset, same years | **+1.9** |
| Omoyo et al. 2015 | Machakos, Kenya: MAM long rains | mean onset, same years | −19.9 (−8.8 with the study's thresholds) |
| BoM northern rainfall onset | Darwin, Australia | median onset vs. "late Oct – early Nov" (taken as 1 Nov) | **+1** |
| Sivakumar 1988 | Niamey, Niger | mean onset 1984–2025 vs. 1904–1984 | +15 |
| Sivakumar 1988, Tables I–II | 17 stations, Niger + Burkina Faso | mean season length | bias +9.8, **MAE 12.5**, r = 0.96 |
| IMD onset over Kerala, per year | 3 Kerala sites | per-year onset, 1984–2025 | bias −33 to −41, r ≈ 0 (definition mismatch, see below) |

_run: 2026-11-15T00:29:45+00:00 · NASA POWER daily 1984–2025 · production criteria (config/onset.yaml)_

**(a) India, 9 cities: median onset vs. IMD new normal onset date (1961–2019)**

| City | lat, lon | Season | IA median onset | IMD normal | Error (days) | False starts |
|---|---|---|---|---|---|---|
| Mumbai | 19.08, 72.88 | JJAS | 05 Jun | 11 Jun | -6 | 17 % |
| Pune | 18.52, 73.86 | JJASO | 05 Jun | 10 Jun | -5 | 15 % |
| Nagpur | 21.15, 79.09 | JJAS | 12 Jun | 16 Jun | -4 | 22 % |
| Bhopal | 23.26, 77.41 | JJAS | 16 Jun | 20 Jun | -4 | 34 % |
| Ahmedabad | 23.03, 72.58 | JJAS | 01 Jul | 26 Jun | +5 | 56 % |
| Jaipur | 26.91, 75.79 | JJAS | 29 Jun | 29 Jun | +0 | 29 % |
| Delhi | 28.61, 77.21 | JJAS | 24 Jun | 27 Jun | -3 | 37 % |
| Patna | 25.59, 85.14 | JJAS | 21 Jun | 16 Jun | +5 | 58 % |
| Varanasi | 25.32, 82.97 | JJAS | 23 Jun | 23 Jun | +0 | 17 % |

Bias -1.3 days, **MAE 3.6 days**, r = 0.92 across cities.

**(b) Kerala: per-year onset vs. IMD monsoon onset over Kerala (1984–2025)**

| Site | n years | IA median | IMD median | Bias (days) | MAE (days) | within ±10 d | r |
|---|---|---|---|---|---|---|---|
| Thiruvananthapuram | 41 | 22 Apr | 02 Jun | -37.8 | 39.2 | 20 % | -0.14 |
| Kochi | 41 | 19 Apr | 02 Jun | -40.5 | 41.7 | 5 % | 0.0 |
| Kozhikode | 41 | 28 Apr | 02 Jun | -32.8 | 32.8 | 15 % | 0.07 |

**(c) West African Sahel / Sudan zone vs. Sivakumar (1988), Niger and Burkina Faso**

Niamey mean onset: IA 27 Jun (1984–2025) vs. Sivakumar 12 Jun (1904–1984): **+15 days**.

| Station | Mean onset | SD (days) | False starts | Failed | Length, Sivakumar | Length, IA (water balance) | Length, IA (Sivakumar's end rule) |
|---|---|---|---|---|---|---|---|
| Niamey | 27 Jun | 18.4 | 24 % | 12 % | 94 | 91.0 | 106.3 |
| Ayorou | 11 Jul | 12.9 | 15 % | 5 % | 67 | 67.7 | 90.6 |
| Birni N'Konni | 03 Jul | 17.2 | 24 % | 5 % | 93 | 82.9 | 95.4 |
| Dosso | 24 Jun | 15.9 | 20 % | 5 % | 99 | 103.7 | 109.5 |
| Maradi | 27 Jun | 16.9 | 15 % | 2 % | 86 | 94.1 | 99.3 |
| Tahoua | 05 Jul | 16.2 | 21 % | 10 % | 76 | 74.2 | 88.5 |
| Zinder | 09 Jul | 11.3 | 15 % | 0 % | 80 | 68.9 | 85.1 |
| Tillabery | 01 Jul | 16.3 | 18 % | 7 % | 81 | 79.9 | 101.8 |
| Say | 25 Jun | 19.2 | 16 % | 10 % | 98 | 100.3 | 110.0 |
| Djibo | 22 Jun | 16.6 | 20 % | 5 % | 83 | 99.9 | 113.4 |
| Dori | 04 Jul | 17.0 | 17 % | 0 % | 85 | 81.8 | 101.6 |
| Markoye | 09 Jul | 17.1 | 18 % | 5 % | 76 | 71.5 | 91.6 |
| Ouagadougou | 08 Jun | 19.2 | 15 % | 2 % | 117 | 134.2 | 134.8 |
| Fada N'Gourma | 04 Jun | 19.1 | 5 % | 5 % | 120 | 140.7 | 142.4 |
| Kaya | 08 Jun | 18.7 | 10 % | 0 % | 107 | 129.0 | 132.2 |
| Po | 10 May | 20.0 | 5 % | 2 % | 125 | 173.7 | 165.7 |
| Leo | 13 May | 23.3 | 8 % | 2 % | 129 | 169.5 | 163.3 |

Season length over 17 stations: water balance (used in the app) bias +9.8 days, **MAE 12.5 days**, r = 0.96; Sivakumar's end rule on POWER rain: bias +18.6, MAE 18.6 days, r = 0.94.

**(d) Kenya, Machakos (bimodal) vs. Omoyo et al. (2015), Machakos station 1979–2009; IA 1984–2009**

| Season | Criteria | n | IA mean onset | Reference mean onset | Error (days) | Failed seasons |
|---|---|---|---|---|---|---|
| MAM | production | 22 | 18 Mar | 07 Apr | -19.9 | 15 % |
| OND | production | 24 | 30 Oct | 28 Oct | +1.9 | 8 % |
| MAM | study thresholds (≥ 4.95 mm rain day, 10-day spell) | 13 | 29 Mar | 07 Apr | -8.8 | 50 % |
| OND | study thresholds (≥ 4.95 mm rain day, 10-day spell) | 10 | 31 Oct | 28 Oct | +2.8 | 62 % |

**(e) Australia, Darwin (southern hemisphere, season across New Year) vs. Bureau of Meteorology**

IA median onset 02 Nov (NDJFMA, n = 41); BoM's 50 mm rule computed on the same POWER rain: 22 Oct; BoM: the western Top End usually reaches onset by late October or early November. Error vs. 1 Nov: **+1 days**.

### V10 · Global yield benchmark: simulated vs. FAOSTAT national yields, 41 countries, 2000–2024
_run: 2026-11-15 · `scripts/yield_benchmark.py` · outputs in [`docs/validation/yield_benchmark/`](validation/yield_benchmark/) · EXP-12, ADR-022_

**Design.**
- **Reference:** FAOSTAT national yields (QCL, t/ha, 2000–2024) for 13 crops. Cotton is lint: lint production / seed-cotton area. Beans are "Beans, dry".
- **Pairs:** 263 country × crop pairs in 41 countries spanning all four Köppen–Geiger main groups. A pair is included when FAOSTAT harvested area averages ≥ 100,000 ha.
- **Sites:** 761 cropland sites. Each pair gets up to 3 MIRCA2000 0.5° cells with the largest harvested area, at least 2.5° apart. Each site carries MIRCA2000's irrigated share.
- **Sowing and harvest dates**, in order of preference:
  - Sacks et al. (2010) observed calendars: 480 sites;
  - Sacks climate-extrapolated calendars: 198 sites;
  - winter- vs. spring-type wheat/barley decided by a coldest-month rule on the site's POWER climate (< −10 °C → spring type): 39 sites;
  - MIRCA2000 condensed calendars: 2 sites;
  - sugarcane (Jan–Dec in MIRCA2000): rainy-season onset, or the month after the coldest month below 600 mm/yr: 42 sites.
- **Simulation:** the IA season model runs every season 2000–2024 with NASA POWER weather and the loam default soil, both rain-fed and with full irrigation. The two are mixed by the irrigated share and area-weighted to a national value. Alfalfa is not benchmarked: FAOSTAT publishes no forage yields.
- **Level metric:** RMSLE of the 2000–2024 mean (log of simulated/observed), the median ratio and the share of pairs within ±30 %.
- **Calibration check:** **leave-one-country-out**. All factors are refitted without the country, then applied to it.
- **Year-to-year metric:** Pearson r of the linearly detrended series. National trends are mostly technology, which the model does not have.

**Level, before and after calibration** (after = held-out countries):

| Calibration | RMSLE | median sim/obs | mean bias (t/ha) | within ±30 % |
|---|---|---|---|---|
| none (before) | 0.843 | 1.37 | 0.65 | 36% |
| crop (held-out) | 0.631 | 0.96 | -0.37 | 37% |
| crop+zone (held-out) | 0.596 | 0.97 | -0.33 | 41% |
| crop+region (held-out) | 0.512 | 1.0 | -0.1 | 52% |
| crop+region+zone (held-out) | 0.518 | 0.99 | -0.18 | 49% |
| crop+region+irrigation (held-out) | 0.5 | 1.01 | 0.09 | 53% |
| crop+region×crop (ridge)+irrigation (held-out) | 0.488 | 0.99 | -0.01 | 57% |
| crop+region×sensitivity (held-out) | 0.495 | 0.98 | -0.13 | 52% |
| crop+region×sensitivity+irrigation (held-out) | 0.487 | 0.99 | 0.04 | 55% |
| anchored crop+region×sensitivity (held-out) | 0.501 | 1.02 | -0.57 | 54% |
| anchored crop+region×sensitivity+irrigation (held-out) | 0.496 | 1.02 | -0.39 | 54% |

**By crop** (after = held-out country, adopted model; anomaly r = detrended year-to-year correlation, uncalibrated):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| barley | 14 | 1.54 | 0.637 | 1.1 | 0.47 | 71% | 0.28 |
| cassava | 13 | 0.78 | 0.435 | 0.81 | 0.463 | 38% | 0.02 |
| cotton | 18 | 1.37 | 0.816 | 0.84 | 0.381 | 72% | 0.18 |
| dry_bean | 19 | 1.42 | 0.723 | 1.02 | 0.543 | 42% | -0.02 |
| groundnut | 17 | 1.79 | 0.831 | 0.91 | 0.359 | 65% | 0.22 |
| maize | 37 | 2.33 | 1.202 | 1.04 | 0.653 | 57% | 0.25 |
| pearl_millet | 15 | 1.88 | 0.953 | 1.02 | 0.444 | 67% | 0.22 |
| potato | 22 | 1.04 | 0.632 | 0.93 | 0.561 | 41% | 0.11 |
| rice | 22 | 1.03 | 0.549 | 1.09 | 0.467 | 41% | -0.02 |
| sorghum | 18 | 5.83 | 1.584 | 1.02 | 0.596 | 44% | 0.23 |
| soybean | 18 | 1.5 | 0.713 | 1.0 | 0.509 | 56% | 0.45 |
| spring_wheat | 16 | 1.02 | 0.401 | 1.05 | 0.47 | 31% | 0.25 |
| sugarcane | 15 | 0.87 | 0.46 | 0.87 | 0.478 | 60% | -0.01 |
| winter_barley | 7 | 1.18 | 0.34 | 1.0 | 0.128 | 86% | 0.17 |
| winter_wheat | 12 | 1.19 | 0.354 | 1.03 | 0.318 | 58% | 0.17 |

**By Köppen–Geiger main climate group** (of the pair's largest site, from its POWER record):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| arid | 59 | 1.43 | 0.964 | 0.91 | 0.664 | 49% | 0.19 |
| continental | 25 | 1.28 | 0.406 | 1.1 | 0.323 | 60% | 0.22 |
| temperate | 106 | 1.1 | 0.672 | 0.98 | 0.474 | 56% | 0.13 |
| tropical | 73 | 2.2 | 1.046 | 1.02 | 0.432 | 52% | 0.07 |

**By region** (UN M49 based):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| east_asia | 13 | 0.95 | 0.291 | 1.21 | 0.313 | 54% | -0.02 |
| eastern_europe_central_asia | 25 | 1.37 | 0.426 | 1.02 | 0.324 | 60% | 0.23 |
| latin_america | 34 | 1.13 | 0.503 | 0.95 | 0.399 | 56% | 0.11 |
| middle_east_north_africa | 17 | 0.84 | 0.978 | 0.59 | 1.042 | 18% | 0.19 |
| northern_america | 18 | 0.92 | 0.342 | 0.96 | 0.293 | 78% | 0.52 |
| oceania | 5 | 1.14 | 0.462 | 1.37 | 0.387 | 40% | 0.48 |
| south_asia | 34 | 1.47 | 0.718 | 1.04 | 0.551 | 47% | 0.11 |
| southeast_asia | 23 | 1.59 | 0.697 | 1.08 | 0.293 | 61% | -0.01 |
| southern_europe | 9 | 1.09 | 0.305 | 1.07 | 0.248 | 78% | 0.48 |
| sub_saharan_africa | 74 | 2.77 | 1.291 | 1.01 | 0.554 | 45% | 0.11 |
| western_europe | 11 | 1.04 | 0.155 | 0.96 | 0.185 | 100% | 0.25 |

**Documented national drought seasons** (harvest year; rank 1 = worst season of 2000–2024 in the linearly detrended series):

| Event | Country | Crop | Year | Rank simulated | Rank FAOSTAT | Sim. anomaly | FAOSTAT anomaly |
|---|---|---|---|---|---|---|---|
| 2012 U.S. Corn Belt drought (USDA ERS) | United States | maize | 2012 | 1/25 | 1/25 | -51 % | -23 % |
| 2012 U.S. drought (USDA ERS) | United States | soybean | 2012 | 1/25 | 2/25 | -44 % | -11 % |
| 2010 Russian heatwave and drought (FAO GIEWS) | Russia | wheat | 2010 | 1/25 | 2/25 | -53 % | -15 % |
| 2012 Kazakhstan drought (FAO GIEWS) | Kazakhstan | wheat | 2012 | 3/25 | 2/25 | -50 % | -28 % |
| 2006 Millennium Drought (ABARES) | Australia | wheat | 2006 | 3/25 | 2/25 | -24 % | -38 % |
| 2018–19 eastern Australia drought (ABARES) | Australia | wheat | 2019 | 7/25 | 1/25 | -16 % | -42 % |
| 2015–16 El Niño drought, southern Africa (FAO GIEWS) | South Africa | maize | 2016 | 2/25 | 2/25 | -38 % | -26 % |
| 2015–16 El Niño drought (FAO GIEWS) | Zambia | maize | 2016 | 7/25 | 15/25 | -6 % | +3 % |
| 2015–16 El Niño drought (FAO GIEWS) | Zimbabwe | maize | 2016 | 2/25 | 2/25 | -29 % | -52 % |
| 2015–16 El Niño drought (FAO GIEWS) | Malawi | maize | 2016 | 6/25 | 2/25 | -10 % | -29 % |
| 2008–09 Pampas drought (Bolsa de Cereales) | Argentina | soybean | 2009 | 13/25 | 2/25 | -0 % | -30 % |
| 2017–18 Pampas drought (Bolsa de Cereales) | Argentina | soybean | 2018 | 3/25 | 3/25 | -18 % | -16 % |
| 2022–23 Pampas drought (Bolsa de Cereales) | Argentina | soybean | 2023 | 2/25 | 1/25 | -23 % | -39 % |
| 2015–16 Morocco drought (FAO GIEWS) | Morocco | wheat | 2016 | 4/25 | 5/25 | -9 % | -35 % |
| 2007 Morocco drought (FAO GIEWS) | Morocco | wheat | 2007 | 3/25 | 2/25 | -10 % | -54 % |
| 2004–05 Iberian drought (AEMET) | Spain | barley | 2005 | 3/25 | 2/25 | -25 % | -45 % |
| 2011–12 Iberian drought (AEMET) | Spain | barley | 2012 | 5/25 | 4/25 | -18 % | -24 % |
| 2022–23 Iberian drought (AEMET) | Spain | wheat | 2023 | 8/25 | 1/25 | -8 % | -43 % |
| 2018 central-European drought (DWD) | Germany | wheat | 2018 | 6/25 | 2/25 | +0 % | -11 % |
| 2003 European heatwave (Ciais et al., 2005) | France | wheat | 2003 | 4/25 | 3/25 | -3 % | -11 % |
| 2002 monsoon failure (IMD) | India | rice | 2002 | 1/25 | 1/25 | -5 % | -6 % |
| 2009 monsoon failure (IMD) | India | rice | 2009 | 6/25 | 2/25 | -2 % | -5 % |
| 2011 Mexico drought and Sinaloa freeze (SIAP) | Mexico | maize | 2011 | 4/25 | 2/25 | -3 % | -11 % |
| 2020 Ukraine drought (FAO GIEWS) | Ukraine | maize | 2020 | 10/25 | 1/25 | +1 % | -23 % |
| 2008–09 Kenya long-rains failure (FEWS NET) | Kenya | maize | 2009 | 2/25 | 1/25 | -16 % | -20 % |

**Year-to-year signal** (independent of the calibration, which only scales the level):
- Median detrended r = **0.14**. r is positive for 66 % of the pairs and above 0.4 for 23 %.
- 13 of 25 documented national drought seasons are among the 3 worst simulated seasons, and 17 of 25 among the 5 worst. FAOSTAT itself has 22 of 25 in its worst 3.
- The skill is concentrated in rain-fed, water-limited systems: U.S. maize and soybean, Russian and Kazakh wheat, Australian wheat, southern-African maize, Pampas soybean and Iberian cereals.
- It is near zero for irrigated or humid-tropical crops (rice, sugarcane, cassava, East and Southeast Asia), where national yields are driven by management, pests, prices and irrigation supply that the model does not see.

**Interpretation.**
- **The uncalibrated model:**
  - It is near the level of high-input systems: Northern America, Western and Southern Europe, RMSLE 0.16–0.34.
  - It overestimates low-input systems by a factor of 2–6: sub-Saharan Africa median ×2.8, sorghum ×5.8.
  - This is expected: `typical_yield_t_ha` describes well-managed fields.
- **The calibration** (15 crop potential factors with 15 yield-gap sensitivities, and 8 regional gap factors; reference regions fixed at 1):
  - It cuts held-out RMSLE from **0.84 to 0.50**. Pairs within ±30 % rise from **36 % to 54 %**.
  - Sub-Saharan Africa goes from ×2.77 to ×1.01 (RMSLE 1.29 → 0.55).
- **Still weak after calibration:**
  - Middle East & North Africa: RMSLE 1.04, worse than before. Irrigated Egypt and rain-fed Morocco and Türkiye share one factor. MIRCA's site choice puts Morocco's maize on an irrigated cell, while national maize is rain-fed.
  - East Asia and Oceania (one country each): the held-out level is ×1.2–1.4 too high.
  - Sugarcane, cassava, potato and rice: the yield-gap structure explains little for these crops.
- **Not adopted:** a Köppen-zone factor. It made held-out errors worse once the region was known: 0.518 vs. 0.512 (EXP-12).

### V11 · Global pest and disease models against documented outbreaks (NASA POWER only)
_run: 2026-11-15, `scripts/validate_pest_disease.py` → `docs/validation/pest_disease.json`_

**Method.**
- Weather is NASA POWER only: hourly T2M, RH2M, T2MDEW and PRECTOTCORR (available from 2001), and daily data from 1984.
- At mountain sites, temperature and dew point are shifted by −6.5 °C/km from the POWER cell's mean elevation to the site (MODELS §5b).
- Each case's expectation was written into the script before the case was first run.
- **Post-hoc change, disclosed:** the first Sigatoka run showed that a wet period lasting several days counted only on the day it started. Every infection model was fixed to count all days a wet period covers, and all hourly cases were re-run. Parameters were not tuned to the results.

| # | Model | Case and reference | Expectation (set before the run) | Result | Verdict |
|---|---|---|---|---|---|
| 1 | Desert locust breeding | Cyclone Mekunu (landfall 26 May 2018) and Cyclone Luban (Oct 2018) rains in the southern Empty Quarter, which started the 2019–20 upsurge (FAO Locust Watch). Point 18.5 N, 51.5 E, 2001–2022. | 2018 ranks 1st | 2018 ranks **1st of 22** (133 favourable days; next highest 2020 with 114, and 2002 with 61). The first favourable day is **2018-05-26**, the day of Mekunu's landfall. | **hit** |
| 1b | Desert locust breeding | 2003 rains in NW Africa that started the 2003–05 upsurge. Points 21.5 N 13.0 W (NW Mauritania) and 24.5 N 11.5 W (Western Sahara). | 2003 in the top 3 | 2003 ranks **3rd** and **4th of 22**. 2015 ranks 1st at both points, and 2010 and 2018 also rank high. The model sees summer rains (first favourable day 12–16 Aug 2003). | **hit / partial** |
| 2 | Late blight, tropical (Wallin) vs Hutton | Toluca Valley, Mexico, 2600 m: some of the world's highest late-blight pressure, in the Jul–Sep rainy season (Grünwald et al. 2000). 2010–2019. | rainy season ≥ 2× dry-season days | Days with SV ≥ 2: **80.7 rainy vs 5.5 dry** (Jan–Mar); the ratio is ≥ 5.6 in every year. Hutton: 40.7 full days in the rainy season. | **hit** (Hutton also works here) |
| 2b | Late blight, tropical vs Hutton | Ecuadorian highlands, Santa Catalina, 3050 m, where blight occurs all year (Andrade-Piedra et al. 2005). Feb–May vs Jul–Sep. | tropical model flags the season; Hutton finds few or no days | Tropical model: **101.9** days with SV ≥ 2 in Feb–May and 26.0 in Jul–Sep. **Hutton: 0 days in every year**, because nights are below 10 °C. | **hit**: the reason the tropical model replaces Hutton |
| 3 | Rice blast (BLASTAM) | Osaki, Miyagi (Tohoku), Jul–Aug 2001–2015. 2003 was a cool, wet *yamase* summer with conditions favouring panicle blast in northern Japan; 2010 was Japan's record-hot summer. | 2003 in the top 3; 2010 in the bottom half | 2003: **12th of 15** on fully favourable days (27), but **tied 1st** on favourable-or-quasi days (61, with 2005, 2006 and 2013). 2010 ranks **14th** (18 days). | **miss** for 2003 (fully favourable); hit for 2010 |
| 4 | Coffee leaf rust | Chinchiná, Caldas, Colombia, 1360 m: the 2008–2011 epidemic, with incidence 53.7 % against 5.8 % in 1991–94 (Avelino et al. 2015). Years 2003–2016. | 2008–11 mean above the other years | Favourable days per year: **346.8 in 2008–11 vs 348.7 in other years**. The model is saturated (300–363 days a year), and 2010 ranks 13th of 14. | **miss** |
| 4b | Coffee rust driver | Avelino et al. 2015: at Chinchiná, the share of days with Tmax 22–28 °C rose from 67 % (1991–94) to 78 % (2008–11). | share higher in 2008–11 | POWER, lapse-corrected by +4.6 °C: **98.1 % → 95.6 %**. The mean daily range *rose* (7.76 → 8.05 °C) instead of narrowing. | **miss**: POWER does not resolve the station-scale signal |
| 5 | Black Sigatoka | Urabá, Colombia (Apartadó, 30 m): pressure is higher in the Apr–Nov rainy season than in the Dec–Mar dry season. 2010–2019. | rainy-season mean score above dry season in most years | Rainy above dry in **10 of 10** years, but both are near saturation (rainy 0.97–1.00, dry 0.82–0.98). | **hit, weak**: little contrast |
| 6 | Gray leaf spot predictors | Paul & Munkvold 2005, Iowa 1998–2002, V4–V12: 85.5–230.5 h at 22–30 °C and 122–330 humid night hours. POWER at Ames, 1 Jun – 5 Jul 2001 and 2002 (POWER hourly starts in 2001). | both inside the published ranges | 2001: **327 h** warm (above the range) and **174 h** humid nights (inside). 2002: **403 h** (above) and **82 h** (below). | **partial / miss**: gridded 2 m air is warmer and drier than in-canopy sensors |

**Not validated:**
- *Wheat leaf and stem rust:* no open, year-resolved outbreak record matched to a POWER cell was found in time. The parameters are the published ones (Magarey Table 2 and Roelfs et al.), not fitted.
- *Cassava whitefly:* the Katono et al. 2021 counts are not public as a series.
- *Fall armyworm generations:* there was no year-resolved field record to compare against.

### V12 · Outdoor WBGT (heat-stress card): implementation check and fallback error
_run: 2026-11-15T00:42:14+00:00 · script: `scripts/validate_wbgt.py` → `docs/validation/wbgt.json`_

**(a) Independent implementation.** IA's Liljegren et al. (2008) solver was checked against ECMWF **thermofeel 2.3.0** (`thermofeel.liljegren.wbgt`, separate code) on a 1,800-case grid:
- air temperature 15–45 °C, RH 10–90 %, 2 m wind 0.5–6 m/s, GHI 0–1000 W/m², cos θz 0.3–0.95;
- identical radiation inputs.

| n | bias (°C) | MAE (°C) | max abs (°C) |
|---|---|---|---|
| 1800 | -0.0004 | 0.0007 | 0.0154 |

Six of these cases are frozen as unit tests (`tests/test_heat_solar_fire.py`). This checks the *implementation*, not the physics. For the physics, Liljegren's model is widely used as the reference WBGT approximation (e.g. Kong & Huber 2022, *Earth's Future*, doi:10.1029/2021EF002334, and KNMI operations). Liljegren et al. (2008) and later studies report agreement with measured WBGT of about 1 °C. We did not repeat that comparison (see "What was not validated").

**(b) Psychrometric wet bulb (reference cases).**
- Stull (2011) gives 13.7 °C at 20 °C / 50 %; our implementation of Stull's formula reproduces 13.7 °C.
- Over 10–40 °C and 20–80 % RH, Liljegren's psychrometric wet bulb lies -0.67 to -0.04 °C from the Assmann psychrometer equation (γ = 6.62·10⁻⁴ K⁻¹). It is lowest in hot, dry air, and its MAE against Stull is 0.37 °C.
- The natural wet bulb used in WBGT adds radiative heating of the wick on top of this.

**(c) Offline fallback vs. full NASA POWER hourly inputs** (daily-max WBGT). When the hourly forecast with wind and radiation is unavailable, the card uses hourly T/RH with NASA POWER *climatological* wind and sunshine.

| Site, period | days | mean daily-max WBGT, full (°C) | fallback bias (°C) | MAE (°C) | same risk level |
|---|---|---|---|---|---|
| Ludhiana, India (hot, dry pre-monsoon) | 28 | 32.3 | +0.27 | 0.97 | 89% |
| Fallon, Nevada (desert summer) | 31 | 29.0 | -1.50 | 2.09 | 48% |
| Machakos, Kenya (tropical highland) | 28 | 26.7 | +0.84 | 0.84 | 96% |

- The fallback is good in humid and moderate-wind climates.
- In the calm desert (Fallon) it *underestimates* WBGT. The real afternoon hours there have near-calm winds that a daily-mean wind cannot represent.
- The card therefore lowers its confidence to 0.45 on the fallback and says so in the caveats.
- A 0.5 m/s floor on the 2 m grid wind (KNMI/ECMWF operational practice) was added after this check. It removed single calm hours with WBGT jumps of +5 °C in POWER hourly data, which are not credible at a 50 km grid.

### V13 · Rain: NASA POWER vs. GPM IMERG vs. their blend, against 18 rain gauges on 6 continents (2001–2025)
_run: 2026-11-15 · `scripts/validate_imerg.py` → `docs/validation/imerg.json`_

**Question.** Does GPM IMERG rain, or a POWER/IMERG blend, describe rain at the field better than the NASA POWER (MERRA-2) rain IA used so far? Adopt it only where it helps.

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

**Decision (ADR-025).** The 50/50 daily blend beat POWER alone on daily correlation at **16/18** stations (mean r 0.537 → 0.608), on monthly KGE at **16/18** (0.604 → 0.705) and on 3-month anomaly correlation at **15/18** (0.872 → 0.903), and reduced the mean absolute bias from 23.6 % to 17.9 %. It helped in the tropics (11/12 on each of daily r, KGE, anomaly r) and outside them (5/6 on daily r and KGE). It is therefore adopted in both zones, but only inside the validated band |lat| ≤ 45°. IMERG alone has the best monthly amounts (KGE 0.744) but loses on daily timing at half the stations, and the water balance needs daily timing. For IMERG's ~2-month latency the bridge POWER × (0.5 + 0.5·ratio) improves amounts (KGE better at 12/18) without changing timing.

**Where it did not help.** Bogotá (tropical Andes, 2,550 m): both products overestimate by ~+90 % and the blend is no better. Delhi: KGE fell slightly (0.78 → 0.72) because IMERG is drier there; daily r still rose. Pune (lee side of the Western Ghats): POWER +137 %, IMERG +64 %; the blend halves the error but is still poor (LIMITATIONS).

**Caveat.** IMERG Final is calibrated to GPCC monthly gauge analyses and MERRA-2's corrected rain to CPC gauges; GHCN stations feed both, so this is not a fully independent test, and the monthly scores flatter both products more than the daily ones. Tropical GHCN records are patchy (38–156 usable months at 10 of the 12 tropical stations).

### V14 · Regional water storage (GRACE/GRACE-FO) vs. USGS groundwater wells and published GRACE trends
_run: 2026-11-15 · `scripts/validate_grace.py` → `docs/validation/grace.json`_

**Question.** Does IA's water-storage indicator (JPL RL06.3 mascons at the field's cell, harmonic trend model with AR(1)-adjusted significance) move with groundwater where wells exist, and does it reproduce published GRACE trends elsewhere?

**Design.**
- Wells: USGS groundwater-level field measurements (parameter 72019, depth to water), anonymous USGS Water Data OGC API, in a 2° × 2° box (≈ one mascon) around 12 U.S. aquifer regions incl. the Fallon and Ames demo fields. Wells with ≥ 12 years of data in 2003–2025 are kept; the regional index is the median of annual water-level anomalies across wells (≥ 5 wells per year).
- Wells measure hydraulic head (m) and GRACE measures mass (cm of water); without the aquifer's specific yield only co-variation and trend direction are comparable, not magnitude.
- Metrics: r of annual means; agreement of trend sign; agreement of IA's class (declining/likely/stable/rising) with the wells' trend class (OLS on the annual index, same p-value thresholds).

| Region | USGS wells (≥ 12 yrs) | years | r (annual) | well level trend (head) | IA GRACE storage trend | agrees: sign / class |
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

**Summary.** GRACE's annual storage co-varied positively with the regional well index in **11/11** usable regions (median r = **0.56**; 0.86–0.90 in the Central Valley and the Ogallala). The trend direction agreed in **8/11** and the IA class in **7/11**. The declining Ogallala, Central Valley, Snake River Plain, Columbia Plateau and Phoenix basins are all called declining or likely declining. Ames had too few long well records in the USGS database.

**Disagreements, and what we changed because of them.**
- **Fallon (demo field):** 257 wells are flat on median while GRACE's region is falling (−0.38 cm/yr, p = 0.015). The shallow aquifer under the Newlands Project is recharged by flood irrigation and canal seepage, while the ~300 km mascon also sees the drying Great Basin (soil, snow, lakes). We therefore renamed the card from "groundwater falling" to **"regional water reserves falling"**, added "check your well", and state the Fallon disagreement in every GRACE Why.
- **Mississippi Embayment, Long Island:** wells decline slightly, GRACE is flat or rising — the wet humid-climate signal (soil and surface water) dominates the mascon. Central Florida: GRACE rising, wells flat.

**Literature check outside the U.S.** (same period as each study, sign and order of magnitude only — the studies used other solutions and corrections):

| Region | Published GRACE trend | Period | IA, same period | IA, 2002–2026 | Reference |
|---|---|---|---|---|---|
| NW India (Punjab, Haryana, Rajasthan) | -4.0 cm/yr | 2002–2008 | -6.57 cm/yr | -5.48 cm/yr (declining) | Rodell et al. 2009, Nature |
| North China Plain | -2.2 cm/yr | 2003–2010 | -2.81 cm/yr | -1.39 cm/yr (likely declining) | Feng et al. 2013, WRR (groundwater) |
| Tigris–Euphrates–western Iran | -2.7 cm/yr | 2003–2009 | -1.86 cm/yr | -0.55 cm/yr (stable) | Voss et al. 2013, WRR |
| Northern Saudi Arabia aquifers | -0.9 cm/yr | 2002–2016 | -0.50 cm/yr | -0.44 cm/yr (declining) | Rodell et al. 2018, Nature |
| Niger / central Sahel | +1.0 cm/yr | 2002–2016 | +0.76 cm/yr | +1.32 cm/yr (rising) | Rodell et al. 2018, Nature (wetting) |
| California Central Valley | -2.0 cm/yr | 2003–2010 | -1.87 cm/yr | -1.22 cm/yr (likely declining) | Famiglietti et al. 2011, GRL |
{"regions_usable": 11, "median_r_annual": 0.56, "r_positive": "11/11", "trend_sign_agrees": "8/11", "class_agrees": "7/11", "literature_sign_agrees": "6/6"}


Sign agrees **6/6**; magnitudes are within a factor of ~2 of the published values (CRI mascons with JPL scale factors are expected to differ from the spherical-harmonic and GLDAS-corrected numbers of the older studies).

### V15 · Tap-to-detect field boundaries worldwide (Fields of The World, 25 countries)
_Script: `scripts/field_benchmark.py` (sample → run → report). Experiment log: EXPERIMENTS EXP-13. Decision: ADR-026._

**Ground truth.** [*Fields of The World*](https://fieldsofthe.world/) (FTW; Kerner et al., *Fields of The World: A Machine Learning Benchmark Dataset for Global Agricultural Field Boundary Segmentation*, AAAI 2025) publishes vector field boundaries for 24 countries plus Corsica on four continents (`source.coop/kerner-lab/fields-of-the-world-<country>`). Most are government parcel registers (LPIS); Kenya, Rwanda, India, Cambodia, Vietnam and Brazil are hand-annotated. Each country keeps its source licence: CC-BY-4.0 (Austria, Brazil, Cambodia, Finland, India, Rwanda, Slovenia, Spain, Vietnam), CC0-1.0 (Denmark, Luxembourg, Netherlands, Slovakia), CC-BY-2.0 (Corsica), CC-3.0 as listed by FTW (Estonia), Licence Ouverte, IGN RPG (France), DL-DE/BY-2.0 (Germany), open-data terms (Belgium, Croatia, Sweden), CC-BY-NC-4.0 (Latvia, Portugal), non-commercial use only (Lithuania), CC-BY-NC-SA-4.0 (South Africa) and GPL-2.0-or-later (Kenya). The polygons are **not redistributed**. The repo holds only field ids and tap points (`docs/validation/field_benchmark_sample.csv`) and per-field scores (`docs/validation/field_benchmark_{before,after}.json`).

**Protocol.**
- **Sample:** 467 fields, stratified by country and size class: S < 0.5 ha, M 0.5–2, L 2–10, XL 10–150 ha. Four fields per class in each held-out country, eight in each development country; Kenya and Vietnam lack some classes. Seed 2026.
- **Taps:** one simulated tap per field, a uniformly random point at least min(10 m, 15 % of √area) inside the boundary.
- **Detector run:** the production code path (`engine.fields.detect_field`) on the imagery the app uses: Esri World Imagery, 3 × 3 tiles at zoom 17, retried at zoom 16 when the field touches the window edge.
- **Scores:**
  - IoU of the returned polygon with the FTW polygon, in local UTM.
  - Boundary F-score: share of each outline's points (every 1 m) within 5 m of the other outline.
  - A failed detection scores 0.
- **Country split (fixed before any tuning):**
  - DEV = Austria, France, India, Netherlands, Spain. Used for parameter choices and model selection. The edge model and selector were trained on open orthophotos of AT/FR/ES/NL only, never on Esri imagery and never within ~3 km of a benchmark field.
  - The other **20 countries (314 fields) are held out**: no tuning, no training, scored once.
- **Before** = v2 detector (Felzenszwalb + region growing, EXP-10). **After** = v3 (learned edge map + candidate selection, EXP-13).
- Both runs used the same cached tiles in one process; times exclude tile download.

<!-- FIELDS:BEGIN -->
**Held-out countries (never used for tuning or training)** — mean ΔIoU +0.281 (95 % bootstrap CI +0.245 … +0.318), n = 314

| Country | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |
|---|---|---|---|---|---|---|
| Belgium (Europe) | 16 | 0.26 | **0.64** | +0.38 | 19% → 69% | 0.17 → 0.56 |
| Brazil (S. America) | 16 | 0.22 | **0.27** | +0.05 | 12% → 25% | 0.04 → 0.04 |
| Cambodia (Asia) | 16 | 0.08 | **0.33** | +0.25 | 0% → 25% | 0.02 → 0.29 |
| Corsica (Europe) | 16 | 0.32 | **0.49** | +0.17 | 31% → 44% | 0.20 → 0.43 |
| Croatia (Europe) | 16 | 0.50 | **0.60** | +0.10 | 44% → 56% | 0.46 → 0.58 |
| Denmark (Europe) | 16 | 0.30 | **0.73** | +0.43 | 19% → 81% | 0.21 → 0.62 |
| Estonia (Europe) | 16 | 0.32 | **0.58** | +0.26 | 25% → 56% | 0.17 → 0.53 |
| Finland (Europe) | 16 | 0.33 | **0.68** | +0.35 | 31% → 75% | 0.19 → 0.55 |
| Germany (Europe) | 16 | 0.17 | **0.39** | +0.22 | 12% → 38% | 0.09 → 0.31 |
| Kenya (Africa) | 12 | 0.12 | **0.36** | +0.24 | 8% → 42% | 0.05 → 0.20 |
| Latvia (Europe) | 16 | 0.17 | **0.44** | +0.27 | 0% → 44% | 0.10 → 0.37 |
| Lithuania (Europe) | 16 | 0.38 | **0.60** | +0.21 | 31% → 56% | 0.28 → 0.61 |
| Luxembourg (Europe) | 16 | 0.25 | **0.63** | +0.38 | 19% → 62% | 0.17 → 0.58 |
| Portugal (Europe) | 16 | 0.05 | **0.47** | +0.42 | 0% → 44% | 0.01 → 0.39 |
| Rwanda (Africa) | 16 | 0.11 | **0.50** | +0.39 | 12% → 50% | 0.10 → 0.43 |
| Slovakia (Europe) | 16 | 0.35 | **0.58** | +0.23 | 31% → 62% | 0.28 → 0.43 |
| Slovenia (Europe) | 16 | 0.27 | **0.56** | +0.29 | 19% → 56% | 0.18 → 0.51 |
| South Africa (Africa) | 16 | 0.34 | **0.59** | +0.25 | 31% → 69% | 0.23 → 0.42 |
| Sweden (Europe) | 16 | 0.21 | **0.51** | +0.30 | 12% → 50% | 0.14 → 0.39 |
| Vietnam (Asia) | 14 | 0.03 | **0.49** | +0.46 | 0% → 43% | 0.01 → 0.46 |
| **All** | 314 | 0.24 | **0.52** | +0.28 | 18% → 53% | 0.16 → 0.44 |

| Continent | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |
|---|---|---|---|---|---|---|
| Africa | 44 | 0.20 | **0.49** | +0.30 | 18% → 55% | 0.13 → 0.36 |
| Asia | 30 | 0.06 | **0.40** | +0.35 | 0% → 33% | 0.02 → 0.37 |
| Europe | 224 | 0.28 | **0.56** | +0.29 | 21% → 57% | 0.19 → 0.49 |
| S. America | 16 | 0.22 | **0.27** | +0.05 | 12% → 25% | 0.04 → 0.04 |

| Size class | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |
|---|---|---|---|---|---|---|
| S <0.5 ha | 80 | 0.13 | **0.41** | +0.28 | 10% → 45% | 0.13 → 0.44 |
| M 0.5–2 ha | 80 | 0.18 | **0.54** | +0.37 | 11% → 56% | 0.13 → 0.49 |
| L 2–10 ha | 80 | 0.30 | **0.64** | +0.34 | 26% → 65% | 0.21 → 0.49 |
| XL 10–150 ha | 74 | 0.37 | **0.49** | +0.13 | 26% → 43% | 0.16 → 0.33 |

**Development countries (used for tuning)** — mean ΔIoU +0.335 (95 % bootstrap CI +0.284 … +0.386), n = 153

| Country | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |
|---|---|---|---|---|---|---|
| Austria (Europe) | 32 | 0.24 | **0.62** | +0.38 | 22% → 72% | 0.15 → 0.58 |
| France (Europe) | 32 | 0.33 | **0.55** | +0.23 | 28% → 59% | 0.25 → 0.46 |
| India (Asia) | 25 | 0.06 | **0.47** | +0.41 | 0% → 56% | 0.04 → 0.40 |
| Netherlands (Europe) | 32 | 0.24 | **0.61** | +0.38 | 22% → 62% | 0.15 → 0.53 |
| Spain (Europe) | 32 | 0.28 | **0.58** | +0.30 | 22% → 66% | 0.24 → 0.52 |
| **All** | 153 | 0.24 | **0.57** | +0.34 | 20% → 63% | 0.17 → 0.50 |

| Continent | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |
|---|---|---|---|---|---|---|
| Asia | 25 | 0.06 | **0.47** | +0.41 | 0% → 56% | 0.04 → 0.40 |
| Europe | 128 | 0.27 | **0.59** | +0.32 | 23% → 65% | 0.20 → 0.52 |

| Size class | n | IoU before | IoU after | Δ | IoU ≥ 0.5 | boundary F (5 m) |
|---|---|---|---|---|---|---|
| S <0.5 ha | 40 | 0.10 | **0.38** | +0.28 | 8% → 38% | 0.11 → 0.43 |
| M 0.5–2 ha | 40 | 0.18 | **0.60** | +0.42 | 15% → 62% | 0.16 → 0.57 |
| L 2–10 ha | 40 | 0.30 | **0.69** | +0.39 | 28% → 82% | 0.22 → 0.54 |
| XL 10–150 ha | 33 | 0.39 | **0.63** | +0.24 | 30% → 73% | 0.20 → 0.47 |

Time per tap (imagery cached, one process): median 0.4 s → 0.2 s, 95th percentile 1.7 s → 1.0 s. Runs: before 2026-11-15T01:27:56Z, after 2026-11-15T02:00:15Z.
<!-- FIELDS:END -->

**Demo fields** (the four app presets; no FTW labels exist there). The stored preset outlines of Fallon and Córdoba were *produced by the v2 detector*, so IoU against them is circular (v2 scores ~1.0 by construction). The overlays were therefore also checked by eye (`docs/validation/fields_demo.jpg`).

| Field | IoU v2 vs preset | IoU v3 vs preset | Visual check |
|---|---|---|---|
| Fallon NV (5.5 ha, border-irrigated alfalfa) | 1.00 (circular) | 0.93 | Same field, both correct (5.52 vs 5.53 ha) |
| Ames IA (≈ 48 ha quarter section) | 0.88 | **0.91** | v3 follows the field edge and excludes the farmstead; v2 leaked into the farmstead |
| Córdoba ES (wheat on the Guadalquivir) | 1.00 (circular) | 0.79 | v3 is better: v2 (= the preset) cut the eastern lobe off along a jagged line through the crop; v3 follows the road and olive grove |
| Machakos KE (terraced smallholding; preset = rough rectangle) | 0.22 | 0.24 | Both return one terrace strip of ~0.55 ha (still the known weakness) |

![Demo fields: preset (green), v2 (yellow), v3 (red)](validation/fields_demo.jpg)


## Interpretation

### Where the models are strong
- **Rain (V13).** Blending NASA POWER with GPM IMERG improved daily correlation with gauges at 16 of 18 stations on 6 continents, with the largest gains (+0.12 to +0.16) at Niamey, Bamako, Ouagadougou, Dakar, San Juan, Darwin, Ames and Wagga Wagga.
- **Regional water storage (V14).** GRACE storage moved with groundwater levels in 11/11 U.S. aquifer regions and reproduced the sign of 6/6 published depletion or wetting trends.
- **ET₀ (V1).**
  - At the temperate sites, ET₀ from NASA POWER agrees with ERA5 at daily r ≈ 0.97–0.98 and monthly r ≈ 0.99–1.00.
  - The water-balance driver is therefore robust.
  - At Fallon, POWER's ET₀ is ~11 % lower than ERA5's. The two grids mix desert and irrigated valley differently, and the true field value is unknown. Irrigation amounts carry this uncertainty, which is why the cards say "~50 km grid".
- **Drought years (V5).** The season model, driven only by NASA POWER weather, ranks the documented Iowa droughts of **2012 and 1988** at the very bottom of 40 seasons.
- **Field boundaries (V15).**
  - On 20 countries never used for development, mean IoU more than doubled (0.24 → 0.52), and every country improved.
  - The learned edge model was trained on European orthophotos only. It still transferred to Esri imagery of Vietnam, Rwanda and Kenya.
- **Drought status (V4), Iowa.** In the rain-fed Corn Belt, the blended status tracks the U.S. Drought Monitor closely (ρ ≈ 0.74).
- **Yield level worldwide (V9).**
  - After the FAOSTAT calibration, simulated national yields are within ±30 % for 54 % of 263 country × crop pairs in countries the calibration never saw (36 % before).
  - Documented national droughts appear among the worst simulated seasons in water-limited systems: U.S. 2012, Russia 2010, Kazakhstan 2012, southern Africa 2016, Pampas 2018 and 2023, Morocco 2007, Iberia 2005.

- **Rainy-season onset (V9).**
  - The agronomic onset rule recovers the IMD normal onset dates across India within 3.6 days on average, from Mumbai (11 Jun) to Jaipur (29 Jun).
  - It matches the Machakos short-rains onset of a station study within 2 days, and the BoM onset in Darwin within a day.
  - Sahel season lengths follow Sivakumar's station gradient from 67 to 129 days (r = 0.95).
  - The criteria are published and were not tuned to these references.

### Where they are weak, and why
- **Rainy-season onset in Kerala and the Sudanian south (V9).**
  - **Kerala.** In humid Kerala, pre-monsoon showers in April and May already meet the agronomic criterion (≥ 20 mm in 3 days, no week-long dry spell). The detected onset is therefore ~5 weeks before IMD's onset over Kerala, which is a circulation-based monsoon onset, and does not track its year-to-year changes.
    - For upland sowing this early date is real (Kerala's *virippu* season is sown with the summer showers). It is still not the monsoon onset, and the card says so.
  - **Niamey.** The onset is 15 days later than Sivakumar's mean. His mean covers 1904–1984, mostly before the Sahel drought shifted the season. The 50 km grid, rather than a rain gauge, also plays a part.
  - **Southern Sudan zone.** At Po and Léo the seasons come out 40–50 days longer than Sivakumar's. The detected onsets there fall in mid-May, likely early showers that his station series did not count as onset, and both end rules run into October.
  - **Machakos long rains.** The MAM onset is 3 weeks earlier than the station study's. The study's own thresholds, ≥ 4.95 mm rain days and a 10-day dry spell, halve the gap to 9 days but leave half the seasons without a valid onset on POWER rain.

- **Drought in Nevada (V4).**
  - Agreement with the USDM is only moderate.
  - Farm drought in the Lahontan Valley is a **water-supply** drought: Sierra snowpack and Lahontan Reservoir deliveries. Local rain cannot capture that.
  - Adding a 12-month SPEI helped (EXP-03).
  - The proper fix is snowpack and reservoir data plus GRACE-FO storage (ROADMAP #1–2). GRACE storage is now shown as regional context (V14), but it does not set the drought level.
- **East Africa soil water (V2/V3).**
  - Correlations in Machakos are lower. The causes: bimodal short rains, 50 km rain grids missing convective storms, and known reanalysis biases.
  - Advice there carries lower confidence. Local rain-gauge input would help most.
- **Field boundaries (V15).**
  - Smallholder plots under 0.5 ha (IoU 0.41) and Brazilian fields over 100 ha (0.27) remain weak.
  - FTW parcels are register polygons from 2016–2023, while the Esri image date is unknown, so part of the residual error is label/imagery mismatch, not detector error.
  - Per-country n is 12–32, so per-country differences under ~0.1 are not meaningful.
- **Late blight (V7).**
  - 2009 is among the higher-risk seasons on POWER's grid, but not the top.
  - Hutton criteria were designed for station humidity. The 2009 epidemic was also driven by infected transplants, which weather cannot see.
  - The card therefore says "weather favourable for infection — scout", never "disease present".
- **Global pest and disease models (V11).**
  - They are strongest where the signal is large-scale weather. Cyclone rains in locust recession areas are found to the day. The seasonal and highland behaviour of late blight is right, and in the Ecuadorian highlands the tropical model is the only one that responds: Hutton finds 0 days.
  - They are weakest for coffee rust, black Sigatoka and maize gray leaf spot in the humid tropics. RH ≥ 90 % on a ~50 km grid is met almost every night, so the infection models saturate and cannot separate epidemic years (coffee rust 2008–11 is a clear miss). Avelino's station-scale driver, the narrower daily temperature range, does not appear in POWER at all.
  - BLASTAM ranked the cool 2003 Tohoku summer low on fully favourable days. Its 5-day-mean rule (20–25 °C) treats the coldest spells as non-susceptible; 2003 was top-ranked only when quasi-favourable days are counted.
  - Consequences for the product:
    - Coffee rust and Sigatoka are not shown, because coffee and banana are not IA crops yet. They should get station or in-canopy wetness, or a calibrated threshold, before they are switched on.
    - Gray leaf spot and rice blast cards keep "scout first" wording at moderate confidence.
- **MOD16 (V6).**
  - MOD16 has no irrigation input and is known to underestimate ET over irrigated fields in arid regions.
  - A large gap to the model is *expected* there. It is shown for transparency, not as a calibration target.

- **AI drought classifier outside the U.S. (V8, EXP-11).**
  - A global model (EDO CDI + GDO soil-moisture labels, location-agnostic features) beats the current U.S. model on held-out U.S. counties and on most held-out weak-label regions. On held-out Europe it falls narrowly behind.
  - Outside the U.S. the rule-based blend beats both the current and the global model on within ±1 in every region. The ML models over-predict drought there: high hit rates, high false-alarm ratios.
  - The ML classifier therefore stays U.S.-only, and the rules serve the rest of the world.
  - The weak SMIA labels agree with USDM and CDI only moderately (Spearman 0.49 / 0.54), so those regional numbers are indicative.

- **Year-to-year yields outside water-limited systems (V9).**
  - The median detrended correlation with FAOSTAT is only 0.14.
  - Irrigated and humid-tropical crops show almost no year-to-year skill: rice, sugarcane, cassava, East and Southeast Asia.
  - The model has no pests, prices, irrigation-supply cuts or technology. National averages also mix many fields, which three 50 km weather cells cannot represent.
- **Middle East & North Africa yield level (V9):** irrigated and rain-fed systems share one regional factor, and the held-out error is not reduced.

### What was not validated (and why)
- The GRACE indicator outside the U.S. against wells: open long well records were not found in time for India, the Sahel or Spain; only published GRACE trends were compared (V14).
- IMERG above 45° latitude (snow) and in mountains beyond Bogotá: the blend is switched off poleward of 45°.
- Field-level irrigation timing: this needs farm irrigation logs.
- Absolute yields against sub-national (county/district) statistics: V9 uses national FAOSTAT yields. NASS county data needs an API key (ROADMAP #4).
- Alfalfa and other forages: FAOSTAT publishes no forage yields.
- Rotation scores against field trials: no open dataset fits.
- WBGT against on-site globe/wet-bulb measurements: no open co-located dataset was reachable in time. The check in V12 is implementation plus literature.
- Livestock THI thresholds and residue nutrient numbers are literature values, not validated locally.
- Solar pump sizing is unit-tested against hand calculations (`test_size_system_hand_calculation`), not against installed systems. Costs are indicative.

See also [`EXPERIMENTS.md`](EXPERIMENTS.md) for the experiments that changed the code, and [`LIMITATIONS.md`](LIMITATIONS.md).
