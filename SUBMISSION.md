# Space Apps 2026 submission kit: FieldShift

Everything below is ready to paste into the project submission page. **Human steps** are marked ☐.

## ☐ Before you submit (checklist for the team owner)
- ☐ Make the repository publicly reachable. The current source of truth is the private Gitea (`http://vps-home-node-1:3001/lino/fieldshift`). Push a mirror to GitHub: `git remote add github git@github.com:<you>/fieldshift.git && git push github main --tags`.
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
FieldShift is a free web, iOS and Android app that turns NASA Earth observations into simple farm decisions. A farmer drops a pin, picks a crop and gets at most three action cards for this week, such as "Irrigate 38 mm by Thursday" or "High stripe-rust risk from Friday", each with a one-tap "Why?" showing the NASA data, model, confidence and caveats. Its Field Shift explorer compares the farmer's current crop rotation with three or more alternatives, simulated on 15 seasons of NASA weather at that exact field. They are scored on water, income, soil health, erosion, pest cycles and climate risk.

## High-level summary (long)
Farmers face hotter summers, less reliable rain and declining soil, but NASA's long-term data rarely reaches them in a usable form. FieldShift closes that gap with one engine and four simple views:

1. **This week.** A daily FAO-56 root-zone water balance runs on NASA POWER weather (1984 → today), bridged with a 16-day forecast. It tells irrigated farmers *when* and *how many millimetres* to irrigate for their irrigation method, and warns rain-fed farmers before water stress. Disease models (Hutton late-blight criteria, stripe rust, white mould…) use hourly humidity. Degree-day models time pest scouting. Drought status combines SPI/SPEI with SMAP soil moisture and MODIS vegetation health. An NDVI anomaly triggers "scout this field".
2. **Field Shift (rotations).** The current rotation and its alternatives are simulated over the last 15 seasons at the field. Each is scored on irrigation water, indicative income, a soil-health index (living roots, residue, biological nitrogen), erosion (SRTM slope × erosive rain × bare months), pest-cycle disruption and climate risk. The farmer sets the weights with priority sliders. Every strategy lists why it was suggested, the NASA evidence, its benefits, the information gaps, and the risks that need local review. A month-by-month calendar shows the bare-soil windows.
3. **What if?** The farmer can change the sowing date, irrigation strategy (full, deficit, seasonal allocation), crop, temperature (+°C) or rainfall (%). The app shows the effect on yield in typical and bad years, water use and stress days.
4. **Climate.** Shows how the local season has already changed since 1984: heat days, frost-free season, rain, water deficit, with trend significance.

It runs anywhere on Earth because its backbone data is global. It speaks English, Spanish, French, Swahili, Hindi and German. It works offline from cached advice and needs no account.

FieldShift is validated against independent data:
- ET₀ vs. ERA5: monthly r up to 0.997;
- soil-water dynamics vs. ERA5-Land;
- drought status vs. the U.S. Drought Monitor: ρ = 0.74 in Iowa;
- the 2012 and 1988 droughts come out as the two worst of 40 simulated Iowa seasons.

Its weak spots are reported openly. It is designed to support, never replace, farmer judgement.

**Story used in the demo.** Irrigated alfalfa in Nevada's Lahontan Valley (Fallon), the setting of the challenge's own photo. NASA POWER shows days ≥ 35 °C there doubling since 1984 (26 → 50 a year) while warm-season rain fell (95 → 55 mm). FieldShift shows the trade-offs: split-season alfalfa uses ~45 % less irrigation water, and a teff → winter-wheat break disrupts pest cycles. The same app serves a rain-fed maize smallholder in Machakos, Kenya, in Swahili.

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

The team set the goals, chose the direction and reviewed the outputs. The app itself uses no SI at runtime. All advice is computed deterministically from data with published, cited methods (FAO-56, FAO-33, SPI/SPEI, Hutton criteria). No SI-generated images, video or voice are used in the demo. All visuals are real screen captures of the app.

## Links
- Repository: ☐ `<public GitHub URL>` (source of truth: private Gitea, see above)
- Demo video (30 s): ☐ `<YouTube/Drive URL>`, from file `media/fieldshift-demo-30s.mp4`
- Slides (alternative demo format, 7 slides): outline below (☐ optional export)
- Live app: ☐ `<URL if hosted>`; otherwise `docker compose up --build`

---

## Demo video: script and storyboard (≤ 30 s, English captions, no voice)
The rules allow a ≤ 30 s video, with English subtitles if any speech is not in English. Ours uses on-screen captions only. Any narration recorded later must be English or subtitled.

| t (s) | Shot (real screen capture) | Caption |
|---|---|---|
| 0–3 | Title card: FieldShift logo over a NASA GIBS MODIS image of the Lahontan Valley | "Nevada alfalfa farm. Hotter summers. Less water." |
| 3–7 | Climate tab: "Days ≥ 35 °C" trend chart 1984→2025 | "NASA POWER: hot days doubled since 1984 (26 → 50 a year)." |
| 7–12 | Home on mobile (Replay 15 Jul 2025): irrigation card + drought card | "This week: exactly when and how much to irrigate." |
| 12–16 | Tap "Why?" → soil-water chart with stress line, sources, confidence | "Every number is one tap from its NASA evidence." |
| 16–22 | Rotations tab: priority sliders → strategies compared, calendar strip | "Field Shift: compare rotations on 15 seasons of NASA data." |
| 22–26 | What if? +2 °C, −20 % rain → yield and water change | "Test the future before you plant it." |
| 26–30 | Android + iPhone side by side, Swahili UI, Kenya preset; end card | "Web · iOS · Android · 6 languages · offline. FieldShift." |

## Slide deck outline (alternative format, 7 slides max)
1. **Title.** FieldShift: 40 years of NASA data, turned into this week's farm decisions (team, challenge name).
2. **Problem.** Nevada farmer photo context. Hotter, drier seasons (POWER: heat days 26 → 50 a year). Farmers can't use raw satellite data, and rotation choices are high-stakes.
3. **Solution.** Four views of one engine (This week · Why? · Field Shift · What if?), with phone screenshots.
4. **NASA data → decisions.** A diagram: POWER, SMAP, MODIS, SRTM → FAO-56 water balance, SPI/SPEI, disease and pest models, rotation simulator → cards.
5. **Field Shift explorer.** The Fallon example: current alfalfa vs. split-season (−45 % water) vs. teff → wheat (pest-cycle break), calendar, "needs local review".
6. **Does it work?** Validation numbers (ET₀ r = 0.97–0.99, USDM ρ = 0.74, 2012 = worst of 40 seasons) and honest limits.
7. **Impact and next steps.** Smallholders (Kenya, Swahili, offline), global reach, roadmap (IMERG, GRACE-FO, field maps, extension partners). Call to action.
