Pairs: 263 country × crop, 41 countries, 761 sites. Adopted structure: **anchored crop+region×sensitivity** (ADR-020). After = leave-one-country-out (factors fitted without the country).

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

By crop (after = held-out country, model 'anchored crop+region×sensitivity'):

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

By climate zone (after = held-out country, model 'anchored crop+region×sensitivity'):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| arid | 59 | 1.43 | 0.964 | 0.91 | 0.664 | 49% | 0.19 |
| continental | 25 | 1.28 | 0.406 | 1.1 | 0.323 | 60% | 0.22 |
| temperate | 106 | 1.1 | 0.672 | 0.98 | 0.474 | 56% | 0.13 |
| tropical | 73 | 2.2 | 1.046 | 1.02 | 0.432 | 52% | 0.07 |

By region (after = held-out country, model 'anchored crop+region×sensitivity'):

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

Documented drought seasons (rank 1 = worst of the detrended series):

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
