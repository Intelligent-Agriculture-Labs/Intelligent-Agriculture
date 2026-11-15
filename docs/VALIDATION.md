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

### V9 · Global pest and disease models against documented outbreaks (NASA POWER only)
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

## Interpretation

### Where the models are strong
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
  - The proper fix is snowpack and reservoir data plus GRACE-FO storage (ROADMAP #1–2).
- **East Africa soil water (V2/V3).**
  - Correlations in Machakos are lower. The causes: bimodal short rains, 50 km rain grids missing convective storms, and known reanalysis biases.
  - Advice there carries lower confidence. Local rain-gauge input would help most.
- **Late blight (V7).**
  - 2009 is among the higher-risk seasons on POWER's grid, but not the top.
  - Hutton criteria were designed for station humidity. The 2009 epidemic was also driven by infected transplants, which weather cannot see.
  - The card therefore says "weather favourable for infection — scout", never "disease present".
- **Global pest and disease models (V9).**
  - They are strongest where the signal is large-scale weather. Cyclone rains in locust recession areas are found to the day. The seasonal and highland behaviour of late blight is right, and in the Ecuadorian highlands the tropical model is the only one that responds: Hutton finds 0 days.
  - They are weakest for coffee rust, black Sigatoka and maize gray leaf spot in the humid tropics. RH ≥ 90 % on a ~50 km grid is met almost every night, so the infection models saturate and cannot separate epidemic years (coffee rust 2008–11 is a clear miss). Avelino's station-scale driver, the narrower daily temperature range, does not appear in POWER at all.
  - BLASTAM ranked the cool 2003 Tohoku summer low on fully favourable days. Its 5-day-mean rule (20–25 °C) treats the coldest spells as non-susceptible; 2003 was top-ranked only when quasi-favourable days are counted.
  - Consequences for the product:
    - Coffee rust and Sigatoka are not shown, because coffee and banana are not FieldShift crops yet. They should get station or in-canopy wetness, or a calibrated threshold, before they are switched on.
    - Gray leaf spot and rice blast cards keep "scout first" wording at moderate confidence.
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
