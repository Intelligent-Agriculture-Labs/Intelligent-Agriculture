# Roadmap

1. **Earthdata Login integration** (token in env):
   - ✅ GPM IMERG rain, blended with POWER where validated (ADR-025, V13). Next: IMERG **Late** (~14 h latency) to replace the climatological bridge for the last 2 months, once the GES DISC EULA is approved on the project's Earthdata account; validate above 45° (snow) and in mountains (Bogotá was the one clear failure).
   - ✅ GRACE/GRACE-FO regional water-storage trend (ADR-025, V14). Next: the weekly GRACE data-assimilation groundwater and root-zone **percentiles** (`GRACEDADM_CLSM025GL_7D`, GES DISC, same EULA) as a *current* groundwater-drought indicator; subtract modelled soil moisture and snow (GLDAS) to isolate groundwater; refresh the asset monthly with `scripts/grace_extract.py`.
   - HLS 30 m NDVI for field-scale scouting maps;
   - full ECOSTRESS ET/ESI for stress hotspots.
2. **Snowpack and water-supply drought for irrigated basins:**
   - SNOTEL plus reservoir storage (USBR/USGS NWIS) for the Western US, closing the gap found in EXP-03;
   - water-allocation forecasts for Newlands Project-type districts.
3. **Field-level maps:** draw a field, then show NDVI, ET and LST zones and erosion hotspots (SRTM slope × cover) on a map timeline.
4. **US enrichments listed by the challenge:**
   - SSURGO/Web Soil Survey for soil;
   - CDL for crop history and automatic current-rotation detection;
   - PRISM normals;
   - OpenET (with key) for ET validation and irrigated-field ET;
   - NASS QuickStats (with key) for county yield calibration.
5. **Data assimilation:** an ensemble Kalman filter with in-situ soil-moisture sensors (cheap capacitance probes) and with farmer-reported irrigation.
6. **Process-model ensemble:** run AquaCrop-OSPy alongside the FieldShift season model for crops with AquaCrop parameters; ML yield-anomaly model on NDVI + weather where county statistics exist.
7. **Optional LLM phrasing and translation layer** (flag `FIELDSHIFT_LLM_EXPLAIN`):
   - strictly grounded in the computed numbers, with a post-check that every number in the text appears in the payload;
   - translates the Why steps into all six languages;
   - SMS/USSD and voice delivery for feature phones.
8. **Market layer:** USDA AMS Market News and local price inputs to make the income metric farm-specific.
9. **Co-design and validation with extension services** (UNR Extension in Nevada; KALRO in Kenya); A/B test the card wording with farmers.
