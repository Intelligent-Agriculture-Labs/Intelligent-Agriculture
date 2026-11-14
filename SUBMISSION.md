# Space Apps 2026 submission kit: FieldShift

Everything below is ready to paste into the project submission page. **Human steps** are marked ☐.

## ☐ Before you submit (checklist for the team owner)
- ☐ Make the repository publicly reachable. The current source of truth is the private Gitea (`http://vps-home-node-1:3001/lino/fieldshift`). Push a mirror to GitHub: `git remote add github git@github.com:<you>/fieldshift.git && git push github main --tags`.
- ☐ Build and publish the showcase page: `python3 scripts/build_site.py --repo https://github.com/<you>/fieldshift`, then publish `site/dist` with GitHub Pages. This also bakes the repository URL into the deck: `media/fieldshift-deck.pdf`.
- ☐ Upload the 30-second video [`media/fieldshift-demo-30s.mp4`](media/fieldshift-demo-30s.mp4) to YouTube (unlisted is fine) or Google Drive (anyone with the link), and paste the link below. It has burned-in English captions and no voice, so it meets the subtitle rule.
- ☐ (Optional) Host the app publicly; see `docs/DEPLOYMENT.md#public-hosting-human-step`. Without hosting, judges can run `docker compose up --build` or watch the video.
- ☐ All team members are registered for the same Local Event, and appear on the team page.
- ☐ Tick both checkboxes on the submission page: the requirements/terms box and the original-work/references box.
- ☐ Submit before **Sun 15 Nov 2026, 23:59 local time**.

## Project name
**FieldShift**: 40 years of NASA data, turned into this week's farm decisions

## Challenge
Field Shift: Adapting Farms with NASA Data (https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/)

## High-level summary (short, ~100 words)
FieldShift is a free web, iOS and Android app that turns 40 years of NASA Earth observations into simple farm decisions. A farmer taps their field on satellite imagery, and AI finds the boundary. FieldShift then gives at most three actions for this week, each with a one-tap "Why?" showing the NASA evidence. It also gives a multi-year, science-based rotation plan for every field. The plan is checked against 30 soil-borne diseases and pests, nitrogen, erosion, water and climate, and comes with an optimised alternative and its impact on water, fertiliser, CO₂e, soil and income. It works offline, syncs phone and PC, and fits each week into two SMS in six languages.

## Feature highlights (for judges)
- **Map any field:** tap inside your field on sub-metre imagery; FieldShift detects the boundary (editable by hand). Many fields per farm. Accounts sync phone ↔ PC; sharing by code works without an account.
- **This week:** at most 3 cards: irrigation (FAO-56 water balance on NASA POWER + satellite crop coefficient), drought (SPI/SPEI + SMAP + an **AI classifier** trained on U.S. Drought Monitor maps), disease, pests, frost and heat. Each has a plain-language "Why?".
- **Field from space:** 10 m Sentinel-2 greenness history, detected cuttings and harvests, **AI management zones**, and terrain maps (RUSLE erosion risk and hotspots, wetness, frost hollows, slope) from NASA SRTM.
- **Plan the next years:** a per-field rotation plan over 52 crops, checked year by year against a cited knowledge base (30 pathogens, 22 rules). It says what to change, offers a beam-search optimised plan, and states the **impact** (water, N fertiliser, CO₂e, topsoil, income) with trade-offs.
- **Insights:** 40-year climate trends at the field, What-if scenarios, rotation comparison on 15 simulated seasons.
- **For every farmer:** offline mode, six languages incl. Swahili and Hindi, a plain-language glossary, a first-run guide, and **weekly advice as text that fits two SMS**.
- **NASA data everywhere:** POWER (1984→), SMAP L3E/L4, MODIS, **ECOSTRESS 70 m ET**, SRTM, GIBS. Partner data: Sentinel-2 and ERA5.

## High-level summary (long)
**What it does.** Farmers face hotter summers, less reliable rain and declining soil, but NASA's long-term data rarely reaches them in a usable form. FieldShift turns that data into decisions for each field, in five simple tabs:
1. **Today.** At most three actions for this week, ranked by urgency.
2. **Field.** Satellite and terrain maps of the field.
3. **Plan.** This season, plus the rotation for the next years.
4. **Insights.** Climate trends, What-if scenarios and rotation comparison.
5. **More.** Account, languages, glossary and sharing.

**How it works.**
- **This week.** A daily FAO-56 root-zone water balance runs on NASA POWER weather (1984 → today), bridged with a 16-day forecast and fused with a Sentinel-2 crop coefficient. It tells irrigated farmers *when* and *how many millimetres* to irrigate, and warns rain-fed farmers before water stress.
- **Disease and pests.** Disease models (Hutton late-blight criteria, stripe rust, white mould…) use hourly humidity. Degree-day models time pest scouting.
- **Drought status** combines SPI/SPEI with SMAP soil moisture and MODIS vegetation health, refined by a gradient-boosting classifier trained on 80 U.S. counties.
- **Rotation plan.** The planner models disease carry-over from each pathogen's survival in soil, legume nitrogen credits, bare-soil erosion (RUSLE with NASA rain erosivity and SRTM slopes), and water need and yield. Water and yield are simulated with NASA weather at that field. An optimiser searches the region's cropping system for a better plan, and FieldShift reports its impact on the field: water, fertiliser N, CO₂e (IPCC EF1), topsoil and indicative margin.

**Benefits.** On the demo fields, the suggested plans would:
- cut irrigation by about 19,600 m³ a year on a 5.5 ha Nevada alfalfa field (at a lower margin, which the app states);
- keep about 650 t of topsoil over four years on a 48 ha Iowa field;
- save about 105 kg N/ha (≈ 450 kg CO₂e/ha) over four years on a Kenyan smallholder field.

These are model estimates, not yet measured on farms. FieldShift runs anywhere on Earth because its backbone data is global. It works on cheap phones, offline and by SMS.

**Validation.** FieldShift is validated against independent data:
- ET₀ vs. ERA5: monthly r up to 0.997;
- soil-water dynamics vs. ERA5-Land;
- drought status vs. the U.S. Drought Monitor: ρ = 0.74 in Iowa; the AI classifier is within ±1 category in 89 % of weeks on held-out counties;
- the 2012 and 1988 droughts come out as the two worst of 40 simulated Iowa seasons.

Its weak spots are reported openly. It is designed to support, never replace, farmer judgement.

**Aims.** Next steps:
- co-design with extension services and farmer groups;
- add GPM IMERG rainfall and GRACE-FO groundwater;
- run on-farm trials to measure the real impact.

**Story used in the demo.** Irrigated alfalfa in Nevada's Lahontan Valley (Fallon), the setting of the challenge's own photo. NASA POWER shows days ≥ 35 °C there doubling since 1984 (26 → 50 a year) while warm-season rain fell (95 → 55 mm). The same app serves a rain-fed maize smallholder in Machakos, Kenya, in Swahili.

## How it addresses the challenge
| Challenge ask | FieldShift |
|---|---|
| Combine NASA EO with local information | POWER, SMAP, MODIS, SRTM, GIBS + SoilGrids, farmer inputs (crop, sowing date, irrigation method, water allocation, priorities) |
| Compare ≥ 3 rotation strategies incl. existing | Current + 3–4 ranked alternatives per location, 8 metrics each |
| Why suggested / evidence / benefits / gaps / risks for local review | Five explicit sections per strategy, generated from computed numbers |
| Bare-field periods, vulnerable seasons | Ground-cover calendar; vulnerable months from 1991–2020 NASA normals |
| Water use, N-fixing, erosion, organic matter, pests, market | Water, biological N, erosion index, soil-health index, pest-cycle score, indicative margin |
| Explain terms and uncertainty | A "Why?" for every card: plain summary, numbered reasoning, charts vs. normal, confidence and its reason, caveats, sources |
| Support, not replace, farmer judgement | Disclaimers; "needs local review" lists; confidence on every number |

## NASA data used (with links)
- NASA POWER: https://power.larc.nasa.gov/
- SMAP Enhanced L3 soil moisture (SPL3SMP_E): https://nsidc.org/data/spl3smp_e (accessed via ORNL DAAC subsets: https://modis.ornl.gov/)
- MODIS MOD13Q1 NDVI: https://lpdaac.usgs.gov/products/mod13q1v061/ · MOD16A2GF ET: https://lpdaac.usgs.gov/products/mod16a2gfv061/ · MOD11A2 LST: https://lpdaac.usgs.gov/products/mod11a2v061/
- SRTM: https://www.earthdata.nasa.gov/data/instruments/srtm (via OpenTopoData)
- NASA GIBS imagery: https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api

## Space-agency partner data and other references
- Copernicus ERA5 / ERA5-Land (ECMWF), via Open-Meteo: https://open-meteo.com/ (CC BY 4.0). Partner data listed by the challenge.
- ISRIC SoilGrids 2.0 (CC BY 4.0): https://soilgrids.org/
- U.S. Drought Monitor (validation): https://droughtmonitor.unl.edu/
- FAO-56 (Allen et al. 1998), FAO-33 (Doorenbos & Kassam 1979), and other method references in `docs/MODELS.md`.
- OpenStreetMap tiles (© OpenStreetMap contributors).
- Open-source libraries: FastAPI, NumPy, SciPy, httpx, PyYAML, Expo / React Native, react-native-svg, i18next, Leaflet, Playwright, Jest, Maestro.

## Tools and languages
Python 3.13 (FastAPI, NumPy, SciPy), TypeScript (Expo / React Native, react-native-web), Docker, GitHub Actions (CI), Playwright and Maestro (E2E), Xcode / iOS Simulator, Android SDK / emulator, Gitea, tmux on a Linux data server.

## Use of Super Intelligence (SI) tools
We used an SI coding assistant (Anthropic Claude, via Claude Code / T3 Code) extensively:
- to research data sources;
- to write most of the code, tests and documentation;
- to run and analyse the validation experiments.

The team set the goals, chose the direction and reviewed the outputs. The app itself uses no generative AI at runtime. Its ML models are classical and trained by us (gradient boosting for drought, k-means zones, image segmentation for field boundaries). All advice is computed deterministically from data with published, cited methods (FAO-56, FAO-33, SPI/SPEI, Hutton criteria). No SI-generated images, video or voice are used in the demo. All visuals are real screen captures of the app.

## Links
- Repository: ☐ `<public GitHub URL>` (source of truth: private Gitea, see above)
- Demo video (30 s): ☐ `<YouTube/Drive URL>`, from file `media/fieldshift-demo-30s.mp4`
- Slides (alternative demo format, 7 slides): `media/fieldshift-deck.pdf` (built by `scripts/build_site.py` from `site/deck.html`)
- Live app: ☐ `<URL if hosted>`; otherwise `docker compose up --build`
- Showcase page (no login): ☐ publish `site/dist` (built by `python3 scripts/build_site.py --repo <public URL>`) with GitHub Pages

---

## Demo video: script and storyboard (≤ 30 s, English captions, no voice)
The rules allow a ≤ 30 s video, with English subtitles if any speech is not in English. Ours uses on-screen captions only. Any narration recorded later must be English or subtitled.

Follows the official Space Apps template (0:00 team · 0:02 challenge · 0:05 title + tagline · 0:10 how it works + NASA data · 0:20 future vision). Built by `scripts/make_demo_video.py` from real screen captures.

| t (s) | Shot (real screen capture) | Caption |
|---|---|---|
| 0–2 | Title card | "Team FieldShift · NASA Space Apps Challenge 2026" |
| 2–5 | Insights → climate trends, Fallon, Nevada | "Challenge: Field Shift. In Fallon, Nevada, days above 35 °C doubled since 1984" |
| 5–10 | Welcome screen + This week | "FieldShift: 40 years of NASA data, turned into this week's farm decisions" |
| 10–13.5 | Tap-to-detect field, Sentinel-2 AI zones, terrain zones | "Tap your field: AI finds it. Sentinel-2 zones, SRTM erosion and frost maps" |
| 13.5–17 | This week + "Why?" | "3 actions a week, each one tap from its NASA POWER, SMAP and MODIS evidence" |
| 17–20 | Plan → Next years: impact card, year check | "Rotation plan per field: disease, nitrogen, soil, water, and its impact" |
| 20–25 | Share as text, iPhone, Android | "Web, iOS, Android, offline, SMS, 6 languages: for any farm on Earth" |
| 25–30 | End card | "Next: co-design with farmers · extension services · GPM IMERG · GRACE-FO · on-farm trials" |

## Slide deck outline (alternative format, 7 slides max)
1. **Title.** FieldShift: 40 years of NASA data, turned into this week's farm decisions (team, challenge name).
2. **Problem.** Nevada farmer photo context. Hotter, drier seasons (POWER: heat days 26 → 50 a year). Farmers can't use raw satellite data, and rotation choices are high-stakes.
3. **Solution.** Four views of one engine (This week · Why? · Field Shift · What if?), with phone screenshots.
4. **NASA data → decisions.** A diagram: POWER, SMAP, MODIS, SRTM → FAO-56 water balance, SPI/SPEI, disease and pest models, rotation simulator → cards.
5. **Field Shift explorer.** The Fallon example: current alfalfa vs. split-season (−45 % water) vs. teff → wheat (pest-cycle break), calendar, "needs local review".
6. **Does it work?** Validation numbers (ET₀ r = 0.97–0.99, USDM ρ = 0.74, 2012 = worst of 40 seasons) and honest limits.
7. **Impact and next steps.** Smallholders (Kenya, Swahili, offline), global reach, roadmap (IMERG, GRACE-FO, field maps, extension partners). Call to action.
