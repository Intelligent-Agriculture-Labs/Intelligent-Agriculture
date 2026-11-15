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

<a id="v9"></a>
### V9 · Rainy-season onset, false starts and season length vs. published onset climatologies (31 sites, 3 continents)
_Generated by `scripts/validate_onset.py` (results in `docs/validation/onset_results.json`). It is kept outside the auto-generated block above, so `validation_report.py` does not overwrite it._

The detector settings are the production defaults in `config/onset.yaml`: Sivakumar (1988) onset and a 100 mm water-balance cessation. They were fixed before the references were collected. Every reference was read in the original source; see `REFS` in the script.

**Summary (error = FieldShift − reference, in days)**

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

| City | lat, lon | Season | FieldShift median onset | IMD normal | Error (days) | False starts |
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

| Site | n years | FieldShift median | IMD median | Bias (days) | MAE (days) | within ±10 d | r |
|---|---|---|---|---|---|---|---|
| Thiruvananthapuram | 41 | 22 Apr | 02 Jun | -37.8 | 39.2 | 20 % | -0.14 |
| Kochi | 41 | 19 Apr | 02 Jun | -40.5 | 41.7 | 5 % | 0.0 |
| Kozhikode | 41 | 28 Apr | 02 Jun | -32.8 | 32.8 | 15 % | 0.07 |

**(c) West African Sahel / Sudan zone vs. Sivakumar (1988), Niger and Burkina Faso**

Niamey mean onset: FieldShift 27 Jun (1984–2025) vs. Sivakumar 12 Jun (1904–1984): **+15 days**.

| Station | Mean onset | SD (days) | False starts | Failed | Length, Sivakumar | Length, FieldShift (water balance) | Length, FieldShift (Sivakumar's end rule) |
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

**(d) Kenya, Machakos (bimodal) vs. Omoyo et al. (2015), Machakos station 1979–2009; FieldShift 1984–2009**

| Season | Criteria | n | FieldShift mean onset | Reference mean onset | Error (days) | Failed seasons |
|---|---|---|---|---|---|---|
| MAM | production | 22 | 18 Mar | 07 Apr | -19.9 | 15 % |
| OND | production | 24 | 30 Oct | 28 Oct | +1.9 | 8 % |
| MAM | study thresholds (≥ 4.95 mm rain day, 10-day spell) | 13 | 29 Mar | 07 Apr | -8.8 | 50 % |
| OND | study thresholds (≥ 4.95 mm rain day, 10-day spell) | 10 | 31 Oct | 28 Oct | +2.8 | 62 % |

**(e) Australia, Darwin (southern hemisphere, season across New Year) vs. Bureau of Meteorology**

FieldShift median onset 02 Nov (NDJFMA, n = 41); BoM's 50 mm rule computed on the same POWER rain: 22 Oct; BoM: the western Top End usually reaches onset by late October or early November. Error vs. 1 Nov: **+1 days**.

## Interpretation

### Where the models are strong
- **ET₀ (V1).**
  - At the temperate sites, ET₀ from NASA POWER agrees with ERA5 at daily r ≈ 0.97–0.98 and monthly r ≈ 0.99–1.00.
  - The water-balance driver is therefore robust.
  - At Fallon, POWER's ET₀ is ~11 % lower than ERA5's. The two grids mix desert and irrigated valley differently, and the true field value is unknown. Irrigation amounts carry this uncertainty, which is why the cards say "~50 km grid".
- **Drought years (V5).** The season model, driven only by NASA POWER weather, ranks the documented Iowa droughts of **2012 and 1988** at the very bottom of 40 seasons.
- **Drought status (V4), Iowa.** In the rain-fed Corn Belt, the blended status tracks the U.S. Drought Monitor closely (ρ ≈ 0.74).

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
  - The proper fix is snowpack and reservoir data plus GRACE-FO storage (ROADMAP #1–2).
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
- Field-level irrigation timing: this needs farm irrigation logs.
- Absolute yields against county statistics: the NASS API needs a key (ROADMAP #4).
- Rotation scores against field trials: no open dataset fits.

See also [`EXPERIMENTS.md`](EXPERIMENTS.md) for the experiments that changed the code, and [`LIMITATIONS.md`](LIMITATIONS.md).
