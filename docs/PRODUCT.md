# IA · Intelligent Agriculture — product brief

**One line:** IA turns 40 years of NASA Earth observations into this week's farm decisions and next season's crop-rotation plan, with every answer one tap away from the evidence behind it.

## Users
1. **Smallholder farmers in low-connectivity, rain-fed regions.** Examples: maize/cowpea farmers in Machakos, Kenya. Cheap Android phone, intermittent data, Swahili or English. They need to know when to plant, whether a dry spell is coming, and which rotation spreads risk.
2. **Irrigated family farms in water-short regions.** Example: alfalfa growers in Nevada's Lahontan Valley. Water deliveries are cut in drought years, and they ask whether a different rotation would earn more per unit of water.
3. **Extension agents and agronomists**, who advise many farms. They need the raw layers, exports, methods and uncertainty (Expert mode).

## The three questions every week
| Question | How IA answers |
|---|---|
| **1. Do I need to water, and how much, by when?** | A daily FAO-56 root-zone water balance driven by NASA POWER plus the forecast gives a card like "Irrigate 38 mm by Thu 16". The amount accounts for irrigation-method efficiency. Rain-fed fields get a "stress likely from…" warning with low-cost actions instead. |
| **2. Is anything threatening my crop right now?** | Drought status (SPI/SPEI from 40 years of POWER rain, plus SMAP soil moisture and MODIS vegetation health). Disease risk from hourly humidity and temperature models (Hutton late blight, stripe rust, white mould…). Insect timing from degree-day models. Frost and heat warnings. NDVI anomaly → "scout this field". |
| **3. Is my farm set up for the coming seasons?** | The rotation explorer compares the current rotation with ≥ 3 alternatives. Each is simulated over the last 15 seasons of NASA weather at that exact location and scored on water, income, soil health, erosion, pest cycles and climate risk. The What-if simulator tests sowing dates, deficit irrigation and +°C / −rain scenarios. The Climate view shows how the local season has already changed since 1984. |

## Principles
- **Radically simple surface:**
  - At most 3 cards on the home screen, with traffic-light risk, plain language and big touch targets.
  - Onboarding in under 60 s: pin, GPS or demo preset → crop → planting date → irrigation.
  - No account needed.
- **Depth one tap away:** every card has a "Why?" view with:
  - the data (charts vs. normal) and the model;
  - confidence and caveats;
  - sources with resolution, latency and last date.
- **Honest:**
  - Coarse data is called coarse (e.g. "SMAP pixel is 9 km").
  - Assumptions are stated (e.g. irrigation history).
  - Synthetic data never appears in the product, and the API has a `mock` flag that is always false in production.
- **Works anywhere:** the backbone data (POWER, forecast, SRTM, SoilGrids) is global. Six languages. Offline last-advice view.

## Non-goals (v1)
- Field-level (≤ 30 m) satellite stress maps.
- Prescriptions for pesticide products or doses.
- Market price forecasting.
