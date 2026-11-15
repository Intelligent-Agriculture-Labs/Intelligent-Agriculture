# Challenge, judging criteria and rules — ground truth

Source pages were downloaded 2026-11-14. Raw extracts are kept in `docs/sources/` (`challenge_page_2026-11-14.txt`, `judging_guide_2026-11-14.txt`).

## Challenge: "Field Shift: Adapting Farms with NASA Data" (NASA Space Apps 2026)
URL: https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/ · Difficulty: Intermediate/Advanced · Skills: Arts & Multimedia, Earth Science, Software.

**Background (summary).** Temperatures are shifting, rainfall is less predictable and soil health is declining. Water shortages, erosion, nutrient depletion and extreme weather add uncertainty. Choosing a rotation crop is hard: one that helps soil in one place may use too much water, bring disease, miss the local market or fall outside the growing season somewhere else. NASA's long-term datasets and SI (Super Intelligence — the term the 2026 rules use instead of "AI") can turn this into farmer-friendly insight.

**Objectives.**
- Combine NASA Earth observations with local agricultural information in an app, model, map or decision-support tool that helps farmers explore crop rotations that improve soil health and resilience to weather and water change.
- Datasets named: SMAP, ECOSTRESS, GPM, Landsat, MODIS, NASA POWER, GRACE/GRACE-FO, SRTM.
- Patterns to analyse: temperature, heat stress, rainfall, soil moisture, evaporation, frost risk, extreme precipitation, vegetation stress, long-term water trends.
- Farmer priorities to consider: water use, forage value, N-fixing potential, erosion reduction, organic matter, market suitability.
- Highlight bare-field periods, vulnerable seasons and rotations that interrupt pest cycles, reduce water demand, improve infiltration or add income.
- **Compare at least three rotation strategies, including the existing rotation.** For each, explain why it was suggested, the supporting evidence, its benefits, the information gaps, and the risks that need local review.
- The tool supports farmer judgement and does not replace it.

**Potential considerations.** Explain terms (ET, soil-moisture anomaly, NDVI, frost risk, water balance); satellite vs. ground data; compare SI/statistical approaches; uncertainty and where local expertise is needed; harmonise resolutions; nutrient cycling, erosion, organic matter, pest-cycle disruption, water use, forage, market; maps and timelines and scenario sliders; farmer-centred design and inputs (water availability, equipment, market); reminders about local expertise.

**Resources listed.**
- NASA: SMAP, GPM/IMERG, Landsat, MODIS/VIIRS, NASA POWER, SRTM, ECOSTRESS, NLDAS/GLDAS, GEDI.
- USDA and other US agencies: Ag Data Commons, Web Soil Survey, CDL/CropScape, PRISM, SSURGO/STATSGO2, NAIP, NLCD, CoCoRaHS, USGS NWIS, AMS Market News, NASS QuickStats, OpenET, LANDFIRE.
- International: FAO GAEZ.
- Space-agency partners: ESA/Copernicus Sentinel-2 and ERA5.

## Judging criteria (Judging & Awards Guide) — each scored 1–5
| Criterion | What judges look for |
|---|---|
| **Impact** | Significance of the problem, reach, how inspiring and effective the solution is |
| **Creativity** | Originality and innovation; a fresh perspective |
| **Validity** | Scientifically sound, technically feasible, complete, **usable and user-friendly** |
| **Relevance** | Fully addresses the challenge; **NASA data is integral**, not superficial |
| **Presentation** | Clear, engaging, well-structured story; the demo *and* the full project are judged; weighted as much as the others |

Global awards include Best Use of Science, Best Use of Data, Best Use of Technology, Galactic Impact, Best Storytelling, Global Connection and Local Impact.

## Rules that constrain the deliverables
- **Demo:** a ≤ 30-second video (English subtitles required if speech is not in English) **or** ≤ 7 slides including title and intro. It must be at a public link that needs no login.
- **Deadline:** Sunday **15 Nov 2026, 23:59 local time** of the team's Local Event.
- English on the submission page; all external resources (code, text, images) must be listed in the References field; no copyrighted material without permission.
- **SI disclosure:** "Each team's project submission must include a description of how SI tools were used." SI-generated images and videos must be acknowledged in descriptive text and metadata **and carry a visible watermark**.
- No photos, voices or likenesses of people under 18.
- Team size 1–6; all members registered for the same Local Event.

## Requirement → feature map
| Requirement | IA feature | Criterion |
|---|---|---|
| Use NASA EO data integrally | NASA POWER drives every model (ET₀, water balance, GDD, SPI, climate trends); SMAP, MODIS NDVI/ET/LST and SRTM feed drought, scouting and erosion | Relevance |
| Compare ≥ 3 rotation strategies incl. existing | **Field Shift** view: current rotation + ranked alternatives, 8 metrics, calendar | Relevance, Impact |
| Why suggested / evidence / benefits / gaps / risks for local review | Each strategy card has these five sections, generated from model numbers | Validity, Presentation |
| Bare-field periods, vulnerable seasons | Month × year ground-cover calendar; vulnerable-period list from 1991–2020 POWER normals | Relevance |
| Water use, N-fixing, erosion, organic matter, pest cycles, forage, market | Rotation metrics: irrigation/deficit, biological N, erosion index (SRTM slope × erosive rain × bare months), soil-health index, pest-cycle disruption, gross margin | Relevance, Validity |
| Farmer priorities and constraints | Priority sliders; irrigation method; seasonal water allocation | Validity (usability) |
| Temperature, heat stress, frost, extreme rain, long-term water trends | Climate view (1984→now, Theil–Sen + Mann–Kendall); heat/frost cards | Relevance |
| Explain terms and uncertainty | "Why?" view: plain summary, reasoning steps with numbers, confidence + note, caveats (e.g. 9 km vs. field), sources with resolution and latency | Validity, Presentation |
| Scenario sliders | **What if?**: planting date, irrigation strategy, crop, +°C, rain % | Creativity |
| Interactive maps; field-level vulnerabilities (erosion zones, water-stress/wet spots, frost-prone areas) | **Map** tab: computed terrain layers (elevation, slope, RUSLE erosion, wetness, frost hollows), management zones with planning advice, NASA GIBS true-colour/NDVI | Relevance, Creativity, Presentation |
| SI/AI, data fusion, harmonising resolutions | AI drought classifier (gradient boosting on USDM, county-held-out validated); k-means management zones on 10 m Sentinel-2 + 30 m terrain on one grid; satellite Kcb fused into the water balance; tap-to-detect field boundaries | Creativity, Validity |
| Field-level, any field the farmer has; works across devices | Multiple fields per farm, drawn or auto-detected on sub-metre imagery, synced phone ↔ PC by code/QR without accounts | Impact, Presentation |
| Timelines, planning | **Plan** tab: sowing-window scan, stage dates, pest-scouting timeline, monthly water budget vs. allocation, frost/heat risk calendar | Impact, Validity |
| Support, not replace, local expertise | Disclaimers, "needs local review" lists, confidence on every card | Validity |
| Weekly decisions (build-prompt scope) | **This week**: ≤ 3 ranked action cards for water, drought, disease, pests, frost/heat | Impact |
| Low-connectivity smallholders | Kenya preset, small gzip payloads, offline last-advice cache, six languages incl. Swahili and Hindi | Impact, Global Connection |
| SI disclosure | README §SI use, SUBMISSION.md | Rules |
| 30 s video / 7 slides | SUBMISSION.md storyboard + slide outline; media/ captures | Presentation |
