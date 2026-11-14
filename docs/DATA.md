# Data sources

All sources were verified reachable on 2026-11-14 from both the Mac and the VPS. FieldShift needs **no API keys** by default. Each source sits behind `backend/fieldshift/data/http.py`, which provides:
- a disk cache (TTL by data age);
- retries with exponential backoff;
- per-host rate limiting;
- a fallback chain: fresh cache → live → stale cache → committed demo cache → fuzzy offline match.

| Variable(s) | Source | Provider / licence | Resolution | Latency | Access | Used for | Fallback |
|---|---|---|---|---|---|---|---|
| Tmax, Tmin, T2M, RH, dew point, wind 2 m, all-sky shortwave, **precipitation** (`PRECTOTCORR`, MERRA-2 bias-corrected) | **NASA POWER** daily point API, community AG | NASA LaRC (public domain) | 0.5° × 0.625° meteorology; 1° solar | ~2–5 days (solar can lag) | `power.larc.nasa.gov/api/temporal/daily/point`, no auth | ET₀, water balance, GDD, pests, SPI/SPEI, climate trends, rotations, What-if | Hargreaves ET₀ when radiation is missing; forecast bridges the latency gap |
| Hourly T, RH | NASA POWER hourly API | NASA LaRC | as above | ~days | no auth | Disease validation (2009 late blight) | — |
| Vegetation greenness NDVI | **MODIS Terra MOD13Q1 v061** | NASA LP DAAC via ORNL DAAC subsets (public domain) | 250 m, 16-day | ~2–4 weeks | `modis.ornl.gov/rst/api/v1`, no auth | NDVI anomaly → scouting card; vegetation condition index in drought status; Why charts | Card omitted when unavailable |
| Actual ET | **MODIS MOD16A2GF v061** | NASA LP DAAC via ORNL | 500 m, 8-day | yearly (gap-filled) | ORNL subsets | ET validation | — |
| Land-surface temperature | **MODIS MOD11A2** | NASA LP DAAC via ORNL | 1 km, 8-day | ~2 weeks | ORNL subsets | Expert layer | — |
| Surface soil moisture | **SMAP SPL3SMP_E** (enhanced L3, 9 km) | NASA NSIDC DAAC via ORNL | 9 km, daily (2–3 day revisit) | ~2 days | ORNL subsets | Soil-moisture percentile in drought status; Why chart | Omitted; ERA5-Land used for validation |
| Elevation, slope | **SRTM GL1 (30 m)** via OpenTopoData | NASA/USGS; OpenTopoData (public API) | 30 m | static | `api.opentopodata.org/v1/srtm30m` | Slope → erosion index; elevation → psychrometric constant | POWER grid elevation |
| Soil texture, SOC → available water | **SoilGrids 2.0** | ISRIC (CC BY 4.0) | 250 m | static | `rest.isric.org` | TAW per metre (FAO-56 Table 19 classes) | Loam default (labelled "default") |
| 16-day forecast + past 14 days (daily & hourly T, RH, rain, FAO ET₀) | **Open-Meteo forecast** (ECMWF IFS/GFS/ICON blend) | Open-Meteo (CC BY 4.0) | ~9–25 km | hourly | `api.open-meteo.com`, no key (non-commercial) | Irrigation lookahead, disease risk, frost/heat warnings, bridging POWER latency | Advice without forecast (cards note it) |
| Soil moisture 0–100 cm, ET₀ | **ERA5 / ERA5-Land** via Open-Meteo archive | Copernicus C3S / ECMWF (challenge partner data) | ~9–25 km | ~5 days | `archive-api.open-meteo.com` | Validation of ET₀ and the water balance | — |
| Drought severity (D0–D4 % area by county) | **U.S. Drought Monitor** | NDMC/USDA/NOAA | county, weekly | weekly | `usdmdataservices.unl.edu` | Training labels (AI drought classifier) and validation | — |
| Drought class (Watch / Warning / Alert / recovery) | **EDO Combined Drought Indicator v4.1** | European Commission JRC, Copernicus EMS; © European Union, **CC BY 4.0** | 0.0417°, dekadal, Europe, 2012– | dekadal | `drought.emergency.copernicus.eu/data/Drought_Observatories_datasets/EDO_Combined_Drought_Indicator/` (netCDF, no login) | Training labels and held-out validation for Europe (offline, data box only) | — |
| Soil-moisture index anomaly (z) | **GDO Soil Moisture Index Anomaly v3.0.1** (LISFLOOD) | European Commission JRC, Copernicus EMS; © European Union, **CC BY 4.0** | 0.05°, dekadal, global, 1995– | dekadal | `…/Drought_Observatories_datasets/GDO_Soil_Moisture_Index_Anomaly/` (netCDF, no login) | *Weak* training labels and validation for Australia, South America, Africa, South and East Asia (offline, data box only) | — |
| Crop coefficients, stage lengths, root depth, p, Ky | **FAO-56 / FAO-33** | FAO | — | — | literature | Season model | — |
| Prices / costs | USDA NASS prices received, extension budgets (2023–24, indicative) | USDA (public domain) | national | — | literature, in `config/crops.yaml` | Indicative gross margin | User-editable config |

## Additional sources (maps, planner, SMAP)
| Variable | Source | Provider / licence | Resolution | Access | Used for |
|---|---|---|---|---|---|
| Elevation grid (terrain maps) | **AWS Terrain Tiles** (terrarium PNG, zoom 14) | Mapzen / AWS Open Data. Sources: **NASA SRTM**, USGS 3DEP/NED, others (public) | ~30 m source (10 m U.S.), ~9.5 m·cos(lat) pixels | `s3.amazonaws.com/elevation-tiles-prod`, no auth | Slope, wetness, frost hollows, RUSLE LS, zones |
| Mean annual precipitation | **NASA POWER climatology** API | NASA LaRC | 0.5° | no auth | RUSLE R factor |
| Surface & root-zone soil moisture, root-zone percentile | **SMAP L3E (SPL3SMP_E.006) and L4 (SPL4SMGP.008) via NASA AppEEARS** | NASA NSIDC / GMAO | 9 km, daily / 3-hourly | Earthdata Login (batch job, ADR-012) | Drought status (L4 root-zone percentile), validation V3 |

## Field-scale imagery and analysis
| Data | Source | Licence / provider | Resolution | Access | Used for |
|---|---|---|---|---|---|
| Sentinel-2 L2A surface reflectance + scene classification | Earth Search STAC (Element 84), AWS Open Data COGs | ESA Copernicus (free and open) | 10 m, 5-day | no auth, HTTP range reads | Field NDVI series, phenology, AI zones, satellite Kcb, latest true-colour/NDVI images |
| High-resolution basemap (drawing, detection) | Esri World Imagery | Esri, Maxar, Earthstar Geographics (attribution; terms of use apply) | ~0.3–1 m | tile service | Field drawing; tap-to-detect boundaries |
| U.S. aerial imagery | USDA NAIP via USGS The National Map | public domain | ~0.6–1 m source (tiles to zoom 16) | tile service | Field drawing (U.S.), alternative detection source |
| Sentinel-2 cloudless 2023 mosaic | EOX s2maps.eu | CC BY-NC-SA 4.0 (contains Copernicus data) | 10 m | tile service | Basemap |
| County centroids | U.S. Census Gazetteer 2023 | public domain | — | download | ML training locations |

## Imagery on the map
NASA GIBS WMTS tiles (MODIS Terra true colour / NDVI), `gibs.earthdata.nasa.gov`, no auth. Used only as visual context.

## Not used (yet) and why
- **GPM IMERG, GRACE-FO, full ECOSTRESS, HLS (30 m NDVI):** need Earthdata Login (no token was available). The ORNL ECOSTRESS subsets returned "no data" for the demo sites. These are the first upgrades in ROADMAP.md.
- **OpenET:** needs an API key. **NASS QuickStats:** needs an API key. Yield validation therefore uses documented drought years (VALIDATION.md).
- **Other drought labels considered for the global drought classifier (EXP-11):**
  - Australian Bureau of Meteorology rainfall-deficiency maps. They are rainfall-only, so as labels for a rainfall-driven model they would be close to circular. The BoM copyright terms are also not a blanket open licence.
  - Global SPEIbase (CSIC, ODbL). Climatic and monthly, computed from CRU, and again close to the model's own SPEI features.
  - GDO Risk of Drought Impact for Agriculture. It mixes in exposure and vulnerability, which is not hazard severity.
  - So the weak global label is GDO's modelled soil-moisture anomaly. It is independent of NASA POWER rain, but it is still a single indicator, and we say so wherever it is used.
- **CDL, SSURGO, PRISM:** US-only. FieldShift's backbone is global so smallholders outside the US get the same product; these are planned as US-only enrichments.

## Harmonisation
Everything is reduced to daily point time series at the field location. Coarser grids (POWER ~50 km, SMAP 9 km) are used as they are, and their footprint is stated in each card's caveats. Composites (MODIS 8- and 16-day) stay at their native time step and are compared with same-period climatology (2001→). No resampling invents detail that isn't there.

## Pre-cached demo dataset
`scripts/build_demo_cache.py` (run on the VPS) fetches every source for the demo presets (Fallon NV, Machakos KE, Córdoba ES, Ames IA), runs all endpoints in all six languages, and copies the gzip JSON payloads into `backend/demo_cache/`, which is committed. With `FIELDSHIFT_OFFLINE=1` the API never touches the network.

## Attribution (shown in the app footer and README)
Data: NASA POWER; NASA SMAP, MODIS (LP DAAC/ORNL DAAC); NASA/USGS SRTM; NASA GIBS; ISRIC SoilGrids (CC BY 4.0); Open-Meteo (CC BY 4.0) incl. ECMWF IFS & Copernicus ERA5; U.S. Drought Monitor; European Drought Observatory and Global Drought Observatory (© European Union, CC BY 4.0; Copernicus Emergency Management Service, JRC); FAO-56/FAO-33 crop parameters.
