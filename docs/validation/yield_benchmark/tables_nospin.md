Pairs: 263 country × crop, 41 countries, 761 sites. Adopted structure: **anchored crop+region×sensitivity** (ADR-020). After = leave-one-country-out (factors fitted without the country).

| Calibration | RMSLE | median sim/obs | mean bias (t/ha) | within ±30 % |
|---|---|---|---|---|
| none (before) | 0.861 | 1.41 | 0.76 | 35% |
| crop (held-out) | 0.634 | 0.96 | -0.38 | 38% |
| crop+zone (held-out) | 0.6 | 0.99 | -0.35 | 41% |
| crop+region (held-out) | 0.509 | 0.99 | -0.09 | 51% |
| crop+region+zone (held-out) | 0.516 | 0.98 | -0.17 | 50% |
| crop+region+irrigation (held-out) | 0.497 | 1.01 | 0.1 | 52% |
| crop+region×crop (ridge)+irrigation (held-out) | 0.484 | 0.98 | -0.01 | 58% |
| crop+region×sensitivity (held-out) | 0.491 | 0.96 | -0.12 | 54% |
| crop+region×sensitivity+irrigation (held-out) | 0.483 | 0.98 | 0.05 | 56% |
| anchored crop+region×sensitivity (held-out) | 0.498 | 0.99 | -0.56 | 55% |
| anchored crop+region×sensitivity+irrigation (held-out) | 0.493 | 1.02 | -0.38 | 55% |

By crop (after = held-out country, model 'anchored crop+region×sensitivity'):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| barley | 14 | 1.55 | 0.678 | 1.09 | 0.488 | 71% | 0.23 |
| cassava | 13 | 0.78 | 0.432 | 0.83 | 0.461 | 38% | 0.01 |
| cotton | 18 | 1.38 | 0.823 | 0.84 | 0.386 | 72% | 0.19 |
| dry_bean | 19 | 1.65 | 0.746 | 0.96 | 0.545 | 53% | -0.01 |
| groundnut | 17 | 1.82 | 0.843 | 0.89 | 0.34 | 65% | 0.23 |
| maize | 37 | 2.33 | 1.225 | 1.02 | 0.646 | 59% | 0.23 |
| pearl_millet | 15 | 2.26 | 1.011 | 0.99 | 0.45 | 67% | 0.16 |
| potato | 22 | 1.05 | 0.631 | 0.93 | 0.545 | 41% | 0.05 |
| rice | 22 | 1.03 | 0.548 | 1.09 | 0.463 | 45% | 0.01 |
| sorghum | 18 | 6.1 | 1.617 | 0.99 | 0.587 | 44% | 0.22 |
| soybean | 18 | 1.51 | 0.714 | 1.0 | 0.501 | 50% | 0.45 |
| spring_wheat | 16 | 1.03 | 0.411 | 1.04 | 0.482 | 31% | 0.27 |
| sugarcane | 15 | 0.87 | 0.458 | 0.88 | 0.477 | 60% | 0.0 |
| winter_barley | 7 | 1.18 | 0.385 | 1.05 | 0.151 | 86% | 0.17 |
| winter_wheat | 12 | 1.21 | 0.395 | 1.06 | 0.303 | 67% | 0.17 |

By climate zone (after = held-out country, model 'anchored crop+region×sensitivity'):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| arid | 59 | 1.59 | 0.998 | 0.9 | 0.67 | 49% | 0.14 |
| continental | 25 | 1.28 | 0.412 | 1.11 | 0.325 | 60% | 0.32 |
| temperate | 106 | 1.14 | 0.688 | 0.97 | 0.467 | 58% | 0.13 |
| tropical | 73 | 2.2 | 1.058 | 1.0 | 0.423 | 55% | 0.07 |

By region (after = held-out country, model 'anchored crop+region×sensitivity'):

| | pairs | sim/obs before | RMSLE before | sim/obs after | RMSLE after | within ±30 % after | anomaly r (median) |
|---|---|---|---|---|---|---|---|
| east_asia | 13 | 1.01 | 0.3 | 1.21 | 0.319 | 54% | -0.01 |
| eastern_europe_central_asia | 25 | 1.38 | 0.426 | 1.02 | 0.311 | 64% | 0.24 |
| latin_america | 34 | 1.14 | 0.511 | 0.94 | 0.404 | 56% | 0.12 |
| middle_east_north_africa | 17 | 0.85 | 0.998 | 0.58 | 1.063 | 18% | 0.19 |
| northern_america | 18 | 0.93 | 0.342 | 0.95 | 0.291 | 78% | 0.51 |
| oceania | 5 | 1.38 | 0.526 | 1.57 | 0.456 | 40% | 0.43 |
| south_asia | 34 | 1.51 | 0.743 | 1.05 | 0.546 | 50% | 0.04 |
| southeast_asia | 23 | 1.59 | 0.697 | 1.09 | 0.288 | 57% | -0.01 |
| southern_europe | 9 | 1.1 | 0.312 | 1.07 | 0.251 | 78% | 0.48 |
| sub_saharan_africa | 74 | 2.92 | 1.32 | 0.99 | 0.535 | 49% | 0.1 |
| western_europe | 11 | 1.04 | 0.155 | 0.95 | 0.19 | 100% | 0.25 |

Documented drought seasons (rank 1 = worst of the detrended series):

| Event | Country | Crop | Year | Rank simulated | Rank FAOSTAT | Sim. anomaly | FAOSTAT anomaly |
|---|---|---|---|---|---|---|---|
| 2012 U.S. Corn Belt drought (USDA ERS) | United States | maize | 2012 | 1/25 | 1/25 | -52 % | -23 % |
| 2012 U.S. drought (USDA ERS) | United States | soybean | 2012 | 1/25 | 2/25 | -44 % | -11 % |
| 2010 Russian heatwave and drought (FAO GIEWS) | Russia | wheat | 2010 | 1/25 | 2/25 | -50 % | -15 % |
| 2012 Kazakhstan drought (FAO GIEWS) | Kazakhstan | wheat | 2012 | 3/25 | 2/25 | -48 % | -28 % |
| 2006 Millennium Drought (ABARES) | Australia | wheat | 2006 | 3/25 | 2/25 | -14 % | -38 % |
| 2018–19 eastern Australia drought (ABARES) | Australia | wheat | 2019 | 1/25 | 1/25 | -15 % | -42 % |
| 2015–16 El Niño drought, southern Africa (FAO GIEWS) | South Africa | maize | 2016 | 6/25 | 2/25 | -23 % | -26 % |
| 2015–16 El Niño drought (FAO GIEWS) | Zambia | maize | 2016 | 6/25 | 15/25 | -0 % | +3 % |
| 2015–16 El Niño drought (FAO GIEWS) | Zimbabwe | maize | 2016 | 3/25 | 2/25 | -24 % | -52 % |
| 2015–16 El Niño drought (FAO GIEWS) | Malawi | maize | 2016 | 6/25 | 2/25 | -3 % | -29 % |
| 2008–09 Pampas drought (Bolsa de Cereales) | Argentina | soybean | 2009 | 13/25 | 2/25 | +1 % | -30 % |
| 2017–18 Pampas drought (Bolsa de Cereales) | Argentina | soybean | 2018 | 2/25 | 3/25 | -18 % | -16 % |
| 2022–23 Pampas drought (Bolsa de Cereales) | Argentina | soybean | 2023 | 3/25 | 1/25 | -18 % | -39 % |
| 2015–16 Morocco drought (FAO GIEWS) | Morocco | wheat | 2016 | 11/25 | 5/25 | -1 % | -35 % |
| 2007 Morocco drought (FAO GIEWS) | Morocco | wheat | 2007 | 9/25 | 2/25 | -2 % | -54 % |
| 2004–05 Iberian drought (AEMET) | Spain | barley | 2005 | 4/25 | 2/25 | -21 % | -45 % |
| 2011–12 Iberian drought (AEMET) | Spain | barley | 2012 | 8/25 | 4/25 | -11 % | -24 % |
| 2022–23 Iberian drought (AEMET) | Spain | wheat | 2023 | 11/25 | 1/25 | -4 % | -43 % |
| 2018 central-European drought (DWD) | Germany | wheat | 2018 | 6/25 | 2/25 | +0 % | -11 % |
| 2003 European heatwave (Ciais et al., 2005) | France | wheat | 2003 | 4/25 | 3/25 | -3 % | -11 % |
| 2002 monsoon failure (IMD) | India | rice | 2002 | 1/25 | 1/25 | -5 % | -6 % |
| 2009 monsoon failure (IMD) | India | rice | 2009 | 5/25 | 2/25 | -2 % | -5 % |
| 2011 Mexico drought and Sinaloa freeze (SIAP) | Mexico | maize | 2011 | 4/25 | 2/25 | -0 % | -11 % |
| 2020 Ukraine drought (FAO GIEWS) | Ukraine | maize | 2020 | 10/25 | 1/25 | +0 % | -23 % |
| 2008–09 Kenya long-rains failure (FEWS NET) | Kenya | maize | 2009 | 1/25 | 1/25 | -16 % | -20 % |
