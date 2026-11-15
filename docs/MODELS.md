# Models and methods

The code lives in `backend/fieldshift/science/`; versioned parameters live in `backend/fieldshift/config/`. Equation numbers refer to FAO-56 (Allen et al., 1998) unless stated otherwise.

## <a id="et0"></a>1. Reference evapotranspiration (`et0.py`)
FAO-56 Penman–Monteith, daily (eq. 6):

ET₀ = [0.408 Δ (Rₙ − G) + γ (900 / (T + 273)) u₂ (eₛ − eₐ)] / [Δ + γ (1 + 0.34 u₂)]

- eₛ from Tmax/Tmin (eqs. 11–12); eₐ from dew point (eq. 14), falling back to RHmean (eq. 19) and then to Tdew ≈ Tmin.
- Δ (eq. 13); γ from elevation (eqs. 7–8; SRTM elevation).
- Rₙ = Rₙₛ − Rₙₗ with α = 0.23, Rₛₒ = (0.75 + 2·10⁻⁵ z) Rₐ, and Rₐ from latitude and day of year (eqs. 21–25, 37–39). G = 0.
- Inputs come from NASA POWER: `T2M_MAX`, `T2M_MIN`, `T2MDEW`, `WS2M` (already at 2 m), `ALLSKY_SFC_SW_DWN` (MJ m⁻² d⁻¹).
- Fallback when radiation is missing: Hargreaves–Samani (eq. 52).
- Tested against FAO-56 Examples 2, 8, 14 and 18 (`tests/test_et0.py`; Example 18 Uccle: 3.9 mm/d).

## <a id="water-balance"></a>2. Season model (`cropmodel.py`)
**Phenology (thermal time).**
- GDD = max(0, (min(Tmax, 30) + max(Tmin, Tbase))/2 − Tbase), with Tbase per crop (McMaster & Wilhelm, 1997, method 2).
- The thermal requirement is calibrated per location: GDDreq = mean over the last 15 years of ΣGDD across the crop's FAO-56 season length from the planting date. Progress f = ΣGDD / GDDreq.
- So a +ΔT scenario shortens the season, as it would for a fixed variety.

**Crop coefficient.** The FAO-56 four-stage single-Kc curve (Kc_ini, Kc_mid, Kc_end; stage fractions from Table 11), indexed by f.
- Alfalfa uses repeating cutting cycles (Table 11, "individual cutting periods"), with a cut every 420 °C·d (base 5 °C; ≈ 750 °F·d base 41 °F, the extension rule of thumb).
- The alfalfa season ends at the first killing frost after two months.
- Evergreen tree and fruit crops (coffee, banana; `evergreen: true`) have no cutting cycles. They use the FAO-56 Table 12 mid-season Kc all year while warm enough to grow, and the end-season Kc otherwise. Yₘ is the annual yield of an established stand, pro rata for the part of the year simulated.

**Root-zone water balance** (eq. 85), daily: Dᵣ,ᵢ = Dᵣ,ᵢ₋₁ − Pᵢ − Iᵢ + ETc,adj,ᵢ + DPᵢ.
- TAW = θ-range × Zᵣ. θ-range by texture class (Table 19 mid-points); Zᵣ grows from Zmin to Zmax by the end of the development stage.
- RAW = p·TAW, with p adjusted by p + 0.04(5 − ETc) (Table 22 note).
- Kₛ = (TAW − Dᵣ)/((1 − p) TAW) when Dᵣ > RAW (eq. 84). ETc,adj = Kₛ·Kc·ET₀. Overflow becomes deep percolation.
- Mass closure is unit-tested.
- **Antecedent soil water (EXP-12).** By default (`antecedent_days=180`, annual crops), a fallow bucket over the full root zone runs from 180 days before sowing:
  - it starts at 60 % depletion (left by the previous crop);
  - evaporation is 0.3·ET₀·(1 − D/TAW_max) (stage-2 drying, FAO-56 Ch. 7);
  - rain refills it, and the excess drains.
  
  Its relative depletion sets the initial root-zone depletion. Soil reached by growing roots enters at that depletion instead of at field capacity, so a dry winter carries over into the season. With `antecedent_days=0`, or when the record is too short, the FAO-56 default applies: 30 % initial depletion, deeper soil at field capacity.

**Irrigation strategies.**
- *Full:* refill to field capacity when Dᵣ ≥ RAW.
- *Deficit 75 / 50:* trigger deeper (RAW + 25 % or 45 % of (TAW − RAW)) and refill to 25 % or 50 % depletion.
- *Allocation:* full strategy until the seasonal allocation is used up.
- *Split-season:* no irrigation after a date.
- Gross depth = net / efficiency: drip 0.90, pivot 0.85, sprinkler 0.75, furrow 0.60, flood 0.65 (well-managed border) (typical application efficiencies).

**Yield.**
- FAO-33 / FAO-56 yield response (eq. 90): 1 − Yₐ/Yₘ = Kᵧ (1 − ETₐ/ETₘ).
- Yₘ = typical yield × completion², where completion < 1 if a killing frost ends the season early. For alfalfa, Yₘ = typical yield × (cuts / 4.5).
- Heat: −3 % per day with Tmax ≥ T_heat in mid-season (cap −50 %).
- Frost before 80 % progress: −5 % (initial), −15 % (development), −35 % (mid-season). Frost after 80 % ends the season.
- Diagnostic biomass in the AquaCrop style: B = WP*·Σ(Tr/ET₀) (Steduto et al., 2009), reported for comparison (EXPERIMENTS.md).
- **Global calibration** (`science/yieldcal.py`, ADR-022, VALIDATION V10): Yₐ is multiplied by f_crop × f_region^s_crop from `config/yield_calibration.yaml`.
  - The factors are fitted to FAOSTAT national yields (263 country × crop pairs, 41 countries) and validated leave-one-country-out.
  - f_crop corrects the potential level per crop. It is fitted in Northern America, Western and Southern Europe, where f_region = 1.
  - f_region is the regional yield gap: sub-Saharan Africa 0.39, Southeast Asia 0.50, South Asia 0.62, Latin America 0.78, Eastern Europe & Central Asia 0.79, East Asia 0.86, MENA 0.88, Oceania 0.88.
  - s_crop scales the gap per crop: maize 1.68 and sorghum 1.96 (large gaps), cassava 0.60 and sugarcane 0.20 (small).
  - The region comes from a 0.5° country grid (MIRCA2000 units → UN M49). A location outside the grid, or a `Weather` without a region, is uncalibrated.
  - Annual crops without FAOSTAT series get f_region only; perennials, forages and cover crops get no factor.
  - Water use, irrigation and the year-to-year pattern are not calibrated, only the level.

**Assimilation hook.** `simulate(..., assimilate={date: Dᵣ_obs}, assimilation_weight=α)` nudges the state with Dᵣ ← (1 − α) Dᵣ + α Dᵣ_obs. It is used in the experiments with ERA5-Land; it is not on by default (EXPERIMENTS.md explains why).

## <a id="drought"></a>3. Drought (`drought.py`)
- **SPI-n** (McKee et al., 1993; WMO-No. 1090): n-day rain sums compared with the same calendar window (±7 days) in every year since 1984. Gamma fit (scipy, location fixed at 0), mixed with the probability of zero, then transformed to a normal quantile.
- **SPEI-n** (Vicente-Serrano et al., 2010): the same for P − ET₀, using empirical plotting positions.
- **Percentiles:** SMAP surface soil moisture against its own record; vegetation condition index VCI = (NDVI − NDVImin)/(NDVImax − NDVImin) per 16-day period since 2001.
- **Status:** a weighted blend of indicator levels, following the USDM-style convergence of evidence.
  - SPI thresholds: D0 ≤ −0.5, D1 ≤ −0.8, D2 ≤ −1.3, D3 ≤ −1.6, D4 ≤ −2.0.
  - Weights: SPI-90 0.30, SPEI-90 0.25, SPI-30 0.15, soil-moisture percentile 0.20, VHI 0.10, plus the long-term SPEI-12 at 0.30 (EXP-03).
- **Rain input:** SPI/SPEI use the POWER + GPM IMERG blend where it is adopted (§18). The AI classifier (§13) and the climate trends (§7) keep POWER-only rain: the classifier was trained on POWER features, and trends since 1984 need one homogeneous record (IMERG starts in 1998).
- **Long-term water supply:** the GRACE/GRACE-FO storage trend (§19) is reported in the status and its Why, but has **no weight in the level**: it lags 2–3 months, covers ~300 km, and was not validated against drought-monitor labels.

## <a id="disease"></a>4. Disease risk (`disease.py`)
Hourly T and RH come from the forecast (validation uses POWER hourly). RH ≥ 90 % is the leaf-wetness proxy (Sentelhas et al., 2008).
- **Late blight, Hutton criteria** (AHDB 2017): two consecutive days with Tmin ≥ 10 °C and ≥ 6 h at RH ≥ 90 % → score 1.0. Near misses (4–5 h, or a single day) score 0.6, 0.3 or 0.15.
- **Stripe rust:** the longest run of wet hours at 7–15 °C; 8 h gives score 1 (de Vallavieille-Pope et al., 1995).
- **Powdery mildew:** ≥ 6 consecutive hours at 21–30 °C (Gubler et al., 1999, simplified).
- **White mould, alfalfa leaf diseases, millet downy mildew:** wet hours within a temperature window.
- Score → risk: ≥ 0.85 severe, ≥ 0.55 high, ≥ 0.25 moderate.
- Hutton is applied only outside the tropics (|lat| ≥ 23.44°). Between the tropics the Wallin-based tropical model (§5b) replaces it.

## <a id="pests"></a>5. Insect phenology (`pests.py`)
Degree-days = max(0, (min(Tmax, T_up) + Tmin)/2 − T_low), accumulated from a biofix of 1 January (northern hemisphere) or 1 July (southern).

| Pest | T_low / T_up (°C) | Events (°C·d) | Source |
|---|---|---|---|
| Alfalfa weevil | 9 / 30 | 156 egg hatch, 319 peak larvae, 450 decline | UC IPM; Purdue (48 °F base) |
| Western corn rootworm | 11.1 / 30 | 380 hatch, 570 peak injury, 760 adults | Iowa State Ext. |
| European corn borer | 10 / 30 | 208, 611 flights | Mason et al., 1996 |
| Corn earworm | 12.6 / 33.3 | 420 larvae | UC IPM |
| Colorado potato beetle | 10 / 30 | 105 adults, 300 larvae | Ferro et al., 1985 |
| Cereal aphids | 5 / 30 | 250 build-up | CSU Ext. (indicative) |
| Fall armyworm | 12.6 / 35 | 391 per generation (recurring) | Du Plessis et al., 2020 (see §5b) |

## <a id="global-pest-disease"></a>5b. Global pest and disease risk (`science/leafwet.py`, `science/globalrisk.py`, `engine/risk_cards.py`)
These models extend the advice to the world's major crops and farming regions. Every model gives a daily score from 0 to 1: the share of the published infection or development criteria that the weather met. Score bands: ≥ 0.85 severe, ≥ 0.55 high, ≥ 0.25 moderate. A card needs all four of:
- a host crop;
- a field inside the model's geographic range;
- a crop in its at-risk stage window;
- a score at or above the model's threshold within the next 7 days.

Texts are in `config/pest_disease.yaml` in six languages. Actions are scouting and cultural control; treatment decisions are referred to local thresholds and extension services, and no product is ever named. Validation is in [VALIDATION.md V11](VALIDATION.md).

**Leaf wetness (shared).**
- **Default:** an hour is wet when RH ≥ 90 %, or when rain ≥ 0.1 mm falls in that hour. RH ≥ 90 % performed best overall against sensors in Brazil, Canada, Italy and the U.S. (fraction correct 0.87–0.92; Sentelhas et al. 2008).
- **Alternative:** dew-point depression with hysteresis: wet from T − Td ≤ 1.8 °C until T − Td ≥ 2.2 °C (Rao et al. 1998, as tested by Sentelhas et al. 2008).
- **Missing dew point:** derived from T and RH with the Magnus formula (Alduchov & Eskridge 1996).
- **Wet periods:** runs of wet hours. Dry gaps up to a pathogen-specific length (Magarey's D50 classes) do not end a period. A period counts on every calendar day it covers.

**Generic infection equation** (Magarey, Sutton & Thayer 2005, eqs. 1–2), used for the fungal leaf diseases:

  f(T) = ((Tmax − T)/(Tmax − Topt)) · ((T − Tmin)/(Topt − Tmin))^((Topt − Tmin)/(Tmax − Topt)), with T the mean temperature of the wet period
  W(T) = Wmin / f(T), with no infection if W(T) > Wmax
  score = min(1, wet hours / W(T)), taking the best wet period that starts on each day

| Model | Hosts in IA | Range | Criteria / parameters | Source |
|---|---|---|---|---|
| Rice blast (*Magnaporthe oryzae*) | rice | everywhere rice grows | **BLASTAM:** wet period mean 15–25 °C; wet hours ≥ 17/15/14/13/12/11/11/10 h at 15/16/17/18/19/20/21/22–25 °C; mean of the 5 daily means up to that day 20–25 °C → favourable (1.0). ≥ 10 h with one temperature condition missed → quasi-favourable (0.5). Temperatures fine but too short → 0.5·h/required. Symptoms follow 7–10 d later. | BLASTAM sheets of the Ibaraki and Hiroshima prefectural plant protection offices (table after Yokouchi, Higuchi & Munakata) |
| Wheat leaf rust (*Puccinia triticina*) | winter/spring/durum wheat, triticale, spelt | worldwide | Magarey: Tmin 2.6, Topt 25, Tmax 30 °C; Wmin 5 h, Wmax 16 h; dry gaps > 1 h end a period (D50 "sensitive") | Magarey et al. 2005, Table 2 (*P. recondita*); Roelfs et al. 1992 |
| Wheat stem rust (*P. graminis* f. sp. *tritici*) | wheats, triticale, spelt, barley | worldwide | Magarey: Tmin 2, Topt 18, Tmax 30 °C (germination 2/15–24/30 °C; maximum infection at 18 °C); Wmin 6 h (6–8 h dew needed); Wmax = 3.8 + 3.0·Wmin = 21.8 h (Magarey's regression). The light requirement after dew is not modelled. | Roelfs, Singh & Saari 1992 (CIMMYT), Table 2 and text |
| Late blight, tropical (*Phytophthora infestans*) | potato, tomato | \|lat\| < 23.44° (Hutton is used outside the tropics) | **Wallin severity value** per day, from the longest RH ≥ 90 % period and its mean T. 7.2–11.6 °C: 16/19/22/25 h → SV 1/2/3/4. 11.7–15.0 °C: 13/16/19/22 h. 15.1–26.6 °C: 10/13/16/19 h. Outside 7.2–26.6 °C → 0. Score = SV/4. The 7-day SV sum is shown as evidence. | Wallin 1962; BLITECAST (Krause et al. 1975); Grünwald et al. 2000 for Toluca |
| Maize gray leaf spot (*Cercospora zeae-maydis*) | maize, silage maize, sweet corn | worldwide; 30–120 days after planting | Index of the two best weather predictors over V4–V12: hours at 22–30 °C (observed 85.5–230.5 h) and night hours (20–08 h) with RH ≥ 90 % (122–330 h). Trailing 14-day totals are scaled to the upper end of each range, pro-rated from 30 days: score = ½ (warm/107.6 h + humid nights/154 h), each capped at 1. This is a risk *index*, not the authors' fitted regression. | Paul & Munkvold 2005 |
| Coffee leaf rust (*Hemileia vastatrix*) | coffee *(not yet a IA crop)* | tropics | Magarey: Tmin 12.5, Topt 23, Tmax 32.5 °C (cardinal temperatures of the Kushalappa & Eskes curve; optimum within the 21–25 °C germination optimum); Wmin 6 h (wetness curve zero point); Wmax 21.8 h; dry gap ≤ 2 h. Score ×0.5 on days with Tmax outside 22–28 °C, the band linked to the 2008–2013 epidemics. | Kushalappa & Eskes 1989; Avelino et al. 2015 |
| Black Sigatoka (*Pseudocercospora fijiensis*) | banana *(not yet a IA crop)* | tropics | Magarey: Tmin 20, Topt 26.5, Tmax 35 °C (germination); Wmin 12 h (**assumption** within the 0–18 h range reported); Wmax 48 h; dry gap ≤ 2 h. | Jacome, Schuh & Stevenson 1991; Jacome & Schuh 1992 |
| Whitefly / cassava mosaic vector (*Bemisia tabaci*) | cassava | Africa, Asia (where CMD occurs); 0–120 days after planting | Trailing 30 days. Product of band memberships: mean T 28–30 °C (taper 4 °C), rain 30–150 mm (taper 100 mm), RH 55–70 % (taper 15 %). Card at ≥ 0.55. | Katono et al. 2021 (Uganda) |
| Desert locust breeding (*Schistocerca gregaria*) | all crops | FAO recession area boxes (Sahara–Sahel, Horn of Africa and Red Sea, Arabia, SE Iran–Pakistan–Rajasthan) and 10-year mean rain ≤ 400 mm | score = min(1, 30-day rain / 25 mm) × warm factor (1 at a 30-day mean ≥ 20 °C, 0 at ≤ 15 °C — the warm factor is our assumption); 0 below 10 mm. Card at ≥ 0.55. Awareness only: it links to FAO Locust Watch and the national locust unit. | Symmons & Cressman 2001 (FAO Desert Locust Guidelines); FAO Locust Watch |
| Fall armyworm (*Spodoptera frugiperda*), refined in `pests.py` | maize, sorghum, pearl millet, teff | Americas, Africa, Asia, Oceania | Degree-days above 12.6 °C (upper cut-off 35 °C); 391 °C·d per egg-to-adult generation; recurring generations in the tropics | Du Plessis, Schlemmer & Van den Berg 2020 |

**Considered and not implemented.**
- *Northern corn leaf blight:* the dew and temperature requirements (Levy & Cohen 1983) could not be verified from the paper.
- *EPIRICE:* a full SEIR epidemic model needing crop-age and inoculum state. BLASTAM's day-level criteria fit a 7-day advice card better.
- *Kushalappa & Eskes' coffee rust wetness and temperature equations:* the constants available were OCR'd from a scan and could not be checked.
- *SimCast blight units* (Fry et al. 1983): the table could not be verified within the build.

**Temperature in mountains.**
- Live advice uses the Open-Meteo hourly forecast, which is downscaled to the terrain.
- Validation uses NASA POWER hourly, shifted by the standard lapse rate (−6.5 °C/km) from the POWER cell's mean elevation to the site (dew point shifted equally, RH unchanged). Without this, a ~50 km cell in the Andes can be 5 °C too cold (Chinchiná: cell 2138 m, town 1360 m).

**References (section 5b).**
- Alduchov, O.A., Eskridge, R.E. (1996) *J. Appl. Meteorol.* 35: 601–609.
- Avelino, J. et al. (2015) The coffee rust crises in Colombia and Central America (2008–2013). *Food Security* 7: 303–321. doi:10.1007/s12571-015-0446-9
- Du Plessis, H., Schlemmer, M.-L., Van den Berg, J. (2020) The effect of temperature on the development of *Spodoptera frugiperda*. *Insects* 11: 228. doi:10.3390/insects11040228
- Grünwald, N.J., Rubio-Covarrubias, O.A., Fry, W.E. (2000) Potato late-blight management in the Toluca Valley: forecasts and resistant cultivars. *Plant Disease* 84: 410–416. doi:10.1094/PDIS.2000.84.4.410
- Jacome, L.H., Schuh, W., Stevenson, R.E. (1991) *Phytopathology* 81: 1480. doi:10.1094/Phyto-81-1480
- Jacome, L.H., Schuh, W. (1992) *Phytopathology* 82: 515. doi:10.1094/Phyto-82-515
- Katono, K. et al. (2021) *Insects* 12: 604. doi:10.3390/insects12070604
- Krause, R.A., Massie, L.B., Hyre, R.A. (1975) BLITECAST. *Plant Disease Reporter* 59: 95–98.
- Kushalappa, A.C., Eskes, A.B. (1989) Advances in coffee rust research. *Annu. Rev. Phytopathol.* 27: 503–531.
- Magarey, R.D., Sutton, T.B., Thayer, C.L. (2005) A simple generic infection model for foliar fungal plant pathogens. *Phytopathology* 95: 92–100. doi:10.1094/PHYTO-95-0092
- Paul, P.A., Munkvold, G.P. (2005) Regression and artificial neural network modeling for the prediction of gray leaf spot of maize. *Phytopathology* 95: 388–396. doi:10.1094/PHYTO-95-0388
- Rao, P.S., Gillespie, T.J., Schaafsma, A.W. (1998) Estimating wetness duration on maize ears from meteorological observations. *Can. J. Soil Sci.* 78: 149–154.
- Roelfs, A.P., Singh, R.P., Saari, E.E. (1992) *Rust Diseases of Wheat: Concepts and Methods of Disease Management.* CIMMYT, Mexico. hdl:10883/1153
- Sentelhas, P.C. et al. (2008) Suitability of relative humidity as an estimator of leaf wetness duration. *Agric. For. Meteorol.* 148: 392–400. doi:10.1016/j.agrformet.2007.09.011
- Symmons, P.M., Cressman, K. (2001) *Desert Locust Guidelines 1: Biology and behaviour.* FAO, Rome. FAO Locust Watch: https://www.fao.org/locust-watch/
- Wallin, J.R. (1962) Summary of recent progress in predicting late blight epidemics in United States and Canada. *Am. Potato J.* 39: 306–312.

## <a id="planting"></a>6. Planting-window optimisation
The season model runs for candidate dates (intended date ±35 days, weekly) over 15 past seasons. Score = median − 0.5 × (median − p10), which penalises bad-year downside. The recommended window is every date within 3 % of the best score.

## <a id="climate"></a>7. Climate trends (`climate.py`)
Yearly indicators from POWER (1984 → last complete year):
- warm-season Tmax, winter Tmin, GDD (base 10 °C), frost dates and frost-free days;
- days ≥ 35 °C, annual and warm-season rain, ET₀, water deficit;
- heavy-rain days (≥ the local 95th percentile of wet days), longest dry spell.

Trend: Theil–Sen slope per decade, with Mann–Kendall significance (Kendall's τ). An insight is shown only when p < 0.1.

## <a id="rotations"></a>8. Rotation explorer (`rotation.py`)
Candidates are the farmer's current rotation plus ten templates (`config/rotations.yaml`). Each slot is simulated over the last 15 seasons with the farmer's irrigation method, strategy and allocation. Planting dates: in the tropics, planting starts with the wettest 4-month window of the field's own NASA rainfall; in Mediterranean climates spring crops and barley follow the winter-rain calendar. Everywhere else the observed crop calendar where the field is (Sacks et al. 2010, 0.5° cell or the country median; [§22](#country-economics)) replaces the old northern-temperate default, also over a template's generic "10-01"; only crops without calendar data keep the default shifted by hemisphere. Each slot reports `sowing_source`.

**Feasibility filter.** A strategy is dropped if any slot:
- has < 60 % valid seasons;
- has frost during the season in > 30 % of years; or
- has a median yield < 35 % of typical (too cold, short or dry).

**Metrics.**
- **Water:** mean gross irrigation (irrigated) or ETₘ − ETₐ shortfall (rain-fed), mm/yr. Scored relative to the other candidates (lower is better).
- **Income:** mean gross margin = yield × price − cost + 40 kg N/ha × N price after a legume, with the field's **country** producer price, modelled country cost and the world-market N price ([§22](#country-economics)); shown in USD and in the local currency. Rotation effects:
  - −8 % yield for the same family in consecutive slots;
  - +5 % after a legume;
  - alfalfa seeding year × 0.7, then −10 %/yr after year 4 (stand decline / autotoxicity).
  Scored relative to the other candidates.
- **Soil-health index (0–100):** 40 % living-root months + 30 % residue class + 20 % biological N (cap 100 kg/ha/yr) + 10 % rooting-depth diversity.
- **Erosion (RUSLE-inspired, relative):** Σ months (1 − cover) × erosive-rain share of that month (rain on days ≥ the local 90th percentile), × LS factor (1 + slope%/5, slope from SRTM). Score = 100 × (1 − index/1.5).
- **Pest-cycle disruption:** 50 % family diversity + 50 % penalty on the longest same-family run.
- **Climate risk:** 0.5 × share of failed seasons (< 50 % of median) + 0.3 × heat/frost events + 0.2 × CV of margins.
- **Total score:** priority-weighted mean of the water, income, soil, pest and risk scores; the weights are the farmer's sliders.

**Texts.**
- *Why suggested* comes from the template idea.
- *Evidence* is generated from model numbers (POWER normals, simulated irrigation and yields, SRTM slope).
- *Benefits* lists metrics ≥ 8 points better than the current rotation.
- *Information gaps* and *risks for local review* are rule-based: market, soil test, low-confidence crop parameters, alfalfa autotoxicity, water-right rules, herbicide carry-over.

## <a id="terrain"></a>9. Terrain maps (`terrain.py`, `engine/maps.py`)
**DEM.** A 3 × 3 block of zoom-14 web-mercator terrain tiles (AWS Terrain Tiles, terrarium encoding: NASA SRTM 30 m outside the U.S., USGS 3DEP in the U.S.) is fetched around the field. That gives ~768 × 768 px of ≈ 9.5 m·cos(lat). The DEM is smoothed to the true source scale (~30 m) before derivatives, to avoid "orange-peel" artefacts from oversampling.

| Layer | Method |
|---|---|
| Slope, aspect | Horn (1981) 3 × 3 finite differences; aspect = compass bearing of the downslope direction |
| Hillshade | Burrough & McDonnell (1998); sun from 315° at 45° |
| Flow accumulation | D8 steepest descent (O'Callaghan & Mark 1984), cells processed from highest to lowest; no pit filling |
| Wetness | Topographic wetness index TWI = ln(a / tan β) (Beven & Kirkby 1979), with a = specific catchment area |
| Frost-prone hollows | Topographic position index TPI = z − mean(z within ~300 m) (Weiss 2001). Cold-air-pooling index = clip(−TPI / 8 m) × clip(1 − slope / 8°) |
| **Erosion (RUSLE)** | A = R · K · LS · C · P (Renard et al. 1997) |
| Management zones | Erosion hotspot (A ≥ 10 t/ha/yr, or the worst quarter of the field's at-risk area, so a uniformly erosive field still shows where to act first) > erosion risk (A ≥ 5 t/ha/yr, ≈ tolerable soil loss) > wet (top-10 % TWI on < 3 % slope) > frost hollow (index ≥ 0.5) > productive core, classified on ~90 m-smoothed indices |

RUSLE inputs:
- **R** from NASA POWER mean annual precipitation (Renard & Freimund 1994): R = 0.0483 P¹·⁶¹ for P ≤ 850 mm, else 587.8 − 1.219 P + 0.004105 P².
- **K** by soil texture: OMAFRA mid-values (Stone & Hilborn 2012).
- **LS** after Moore & Burch (1986): (A_s/22.13)^0.4 · (sin β / 0.0896)^1.3, with flow length capped at 120 m.
- **C** by crop type: perennial 0.02, cover 0.05, small grain 0.20, row crop 0.38.
- **P** = 1 (no support practices).

Field statistics use the drawn polygon, or a 150 m radius around the pin.

## <a id="planner"></a>10. Season planner (`engine/planner.py`)
For the next occurrence of the planting date, the season model runs for each of the last 15 seasons:
- **Sowing-date scan:** ±6 weeks in weekly steps, giving median and p10 yield, irrigation, frost risk and heat days. Recommended window as in §6.
- **Stage dates:** median days to the FAO-56 stage boundaries in thermal time, with the 10–90 % spread between years. Perennials get the median cutting dates instead.
- **Pest scouting:** median calendar dates of the first two degree-day events of every pest present in the region.
- **Monthly water budget:** median ET₀, ETc, ETa, rain and gross irrigation per month. With an allocation, the full-irrigation need is simulated too, and coverage = allocation / full need.
- **Risk calendar:** share of years with a damaging frost (crop kill threshold) or ≥ 3 heat days (≥ T_heat) in each month.

## <a id="field-detect"></a>11. Tap-to-detect field boundaries (`science/fielddetect.py`, `science/fieldedge.py`)
The farmer taps inside a field, and an editable polygon comes back in about 1–3 s (CPU only).

**Imagery.** Sub-metre RGB (Esri World Imagery; USDA NAIP option in the U.S.), a 3 × 3 tile window at zoom 17, retried at zoom 16 if the field touches the window edge.

**Pipeline (v3, since EXP-13):**
1. Downsample to ~2.7 m (Lanczos). This removes crop rows and wheel tracks.
2. **Learned edge map.** A tiny U-Net (`models/fieldedge.npz`) predicts, per pixel, the probability of a field boundary B and of field interior X.
   - Architecture: 4 levels with 16-32-64-128 channels; 3 × 3 conv + BatchNorm + ReLU; nearest-neighbour upsampling with skip connections.
   - Size: 0.54 M parameters, float16, 1.0 MB.
   - Inference: plain numpy in `fieldedge.py`, with BatchNorm folded into the convolutions. No deep-learning runtime is needed.
3. **Cost map** E = B + 0.5 (1 − X).
4. **Scale-adaptive candidates.** Flood fills from the tap (snapped to the lowest-cost pixel within 3 px) over {E ≤ t}.
   - t sweeps 24 quantiles of E (20th–98th percentile).
   - Each fill is repeated after a morphological opening of radius 0–3 px, which cuts thin leaks through hedge gaps and farm tracks.
   - The same sweep yields 0.05 ha plots and 100 ha fields, so no field-size parameter is needed.
5. **Learned selection.** Each candidate gets 14 features: log area, area relative to the median candidate, solidity, compactness, mean B on the rim and inside, mean X inside and on the rim, mean E on the rim and inside, border contact, threshold and its rank, and opening radius.
   - 300 gradient-boosted regression trees (`models/fieldselect.npz`, 58 KB, evaluated in numpy) predict the candidate's IoU with the true field.
   - The winner maximises predicted IoU + 0.3 × (rim B − inner B) × solidity². This small prior keeps large uniform fields whole (EXP-13).
6. Fill holes, give back the 1-px boundary, close slits of radius 2 px (irrigation checks, tramlines), trace, and simplify with Douglas–Peucker (1 working pixel).

**Confidence** = the selector's predicted IoU (minus 0.2 if the field touches the window edge), clipped to 0.05–0.95. It ranks results but is not calibrated.

**Fallback.** If the model files are missing, the v2 pipeline runs (`detect_classical`). That is Felzenszwalb segmentation on median-filtered CIE-Lab, plus edge-aware region growing (ΔE < 9 and border gradient < max(p90, 5)); see EXP-10.

**Training (GPU, `scripts/fieldedge/`).**
- **Labels:** Fields of The World (FTW) polygons.
- **Imagery:** open national orthophotos of four countries only, never Esri imagery:
  - France: IGN BD ORTHO, Licence Ouverte 2.0
  - Spain: PNOA, CC-BY 4.0
  - Netherlands: PDOK Luchtfoto, CC-BY 4.0
  - Austria: basemap.at, CC-BY 4.0
- **Windows:** 4,049 web-mercator windows with the app's geometry: 2,800 at zoom 17 and 1,249 at zoom 16. Windows within ~3 km of a benchmark field are excluded.
- **Unlabelled land:** pixels farther than 8 px from a labelled field are ignored in the loss, because registers omit some parcels.
- **Edge model:** boundary BCE (positive weight 4) + Dice, plus interior BCE. Colour, contrast, blur and noise augmentation. 16k steps, batch 32, 160 px crops, about 4 min on an RTX 5070 Ti.
- **Selector:** trained on 1.1 M candidates from 15.9 k simulated taps. The candidates come from *cross-fitted* edge models: FR+ES windows are scored by a model trained on NL+AT, and vice versa. The selector therefore learns from realistic, imperfect edge maps.

**Accuracy (VALIDATION V15).** Measured on 467 FTW fields in 25 countries, with 20 countries held out. Mean IoU on held-out countries rose from 0.24 (v2) to 0.52 (v3), with all 20 held-out countries improving. Smallholder plots under 0.5 ha went from 0.13 to 0.41. On a laptop CPU a window takes a median of 0.5 s (max ≈ 2 s). Smallholder plots and > 100 ha fields remain the hardest cases; see LIMITATIONS.

The polygon always stays editable.

## <a id="satellite"></a>12. Field satellite analytics (`science/satellite.py`, `engine/satellite_service.py`)
**Data.** Sentinel-2 L2A COGs (Earth Search STAC) from the last 12 months, cloud cover < 60 %, up to 24 scenes spread over time. Bands red, NIR and SCL are read through a GDAL WarpedVRT onto a ~10 m web-mercator grid around the field, so scenes from different UTM tiles stack pixel-for-pixel and align with the map. Clear pixels are SCL classes 4/5/6; a scene counts only if ≥ 60 % of the field is clear.

**NDVI series.** Daily linear gap-filling, then a Savitzky–Golay filter (window 31 d, order 2; Chen et al. 2004).

**Phenology.**
- Green-up and senescence at 50 % of the seasonal amplitude (TIMESAT; Jönsson & Eklundh 2004).
- Bare periods: NDVI < 0.20 for ≥ 20 days.
- Season type from prominent peaks (prominence ≥ 0.15): single season, double crop, or repeated cuttings such as alfalfa.

**AI management zones (unsupervised ML).**
- Standardized per-pixel features: mean NDVI, peak NDVI (p90), temporal NDVI variability, slope and wetness (TWI, from the DEM resampled onto the same grid).
- k-means with k ∈ {2, 3, 4} chosen by silhouette score (Rousseeuw 1987); the smallest k wins unless a larger k separates clearly better.
- Zones are ranked by vigour.
- Advice rules use zone wetness and slope relative to the field (waterlogging vs. thin soil on slopes vs. sampling).

**Satellite crop coefficient.**
- fc = (NDVI − 0.15)/(0.85 − 0.15).
- Kcb = 0.15 + (Kcb_full − 0.15) · min(1, 1.5 fc, fc^(1/(1+h))), the FAO-56 density coefficient (Allen & Pereira 2009).

**Data fusion into the water balance.** If a clear scene ≤ 15 days old exists for the field, crop water use from that date is scaled by (Kcb_sat + 0.05)/Kc_model, clipped to 0.4–1.4. The irrigation card's Why shows the numbers, and its confidence rises by 0.1.

## <a id="drought-ml"></a>13. AI drought classifier (`science/drought_ml.py`, `scripts/train_drought_ml.py`)
**Features** (the same code for training and serving), daily from NASA POWER:
- SPI-30/90/180/365 (gamma fit per week-of-year);
- SPEI-like indices on P − ET₀ for the same windows (Gringorten empirical probabilities);
- 30/90-day Tmax anomalies;
- seasonality (sin/cos day of year);
- aridity (ΣP/ΣET₀).

**Labels.** The dominant weekly U.S. Drought Monitor category per county (highest Dk covering ≥ 50 % of the area): 80 counties stratified across the contiguous U.S., 2005–2024, 83,600 samples.

**Model.** scikit-learn HistGradientBoostingClassifier: class-balanced, 300 iterations, learning rate 0.06, 31 leaves, L2 1.0.

**Evaluation.** 5-fold GroupKFold by county, i.e. on counties the model never saw, against the rule-based status on the same samples (EXP-09).

**Use.** The model is used only inside its validated domain (contiguous U.S.), where it replaces the rule level; class probabilities are shown in the Why. Everywhere else the transparent rule-based status is used.

**Global extension (EXP-11, evaluated, not adopted).**
- `scripts/drought_labels_global.py` builds labels for 310 sites in seven regions:
  - U.S.: USDM;
  - Europe: EDO Combined Drought Indicator;
  - Australia, South America, Sub-Saharan Africa, South Asia and East Asia: GDO soil-moisture anomaly, a weak label with thresholds calibrated against USDM.
- `drought_ml.feature_matrix_v2` computes location-agnostic features:
  - SPI/SPEI;
  - lagged SPEI-90;
  - Tmax z-scores;
  - season phase from the locally warmest week;
  - climatological wet-season share and 90-day rain;
  - aridity, mean Tmax and rain seasonality.
- `scripts/train_drought_ml.py` validates with county CV in the U.S., leave-one-region-out and leave-one-climate-zone-out. It adopts a new model only under the rule in EXP-11.
- The run did not meet that rule (Europe held out was slightly worse), so the shipped model and its metadata are unchanged.
- Serving reads `feature_set`, `model_regions` and `served_key` from the metadata:
  - A future adopted model would be served only in the regions where it beat the rules on held-out sites. The region boxes are in `drought_ml.REGION_BOXES`.
  - Old metadata without these fields means: v1 features, U.S. only.

## <a id="sync"></a>14. Farm sync
An account-free farm document (SQLite) is addressed by a random 128-bit id, which stays secret on each device, plus an 8-character pairing code (alphabet without 0/O/1/I). Fields merge per id by `updated_at` (last writer wins); deletions are tombstones. The client pushes 2 s after a change and pulls on start, on focus and every 60 s.

## <a id="rotation-plan"></a>15. Per-field multi-year rotation plan (`science/rotation_plan.py`, `engine/plan_service.py`)
**Inputs.** Field location, outline and irrigation, the farmer's crop history (past years) and plan (next 1–8 years, main crop plus optional cover crop), and priorities.

**Knowledge base** (`config/rotation_knowledge.yaml`, documented in `docs/ROTATION_SCIENCE.md` with references):
- per-crop minimum return interval, self-tolerance and family interval;
- residual N effect and preceding-crop value;
- good/poor predecessors and allelopathy;
- soil-borne pathogens and pests with host lists, survival and recommended break years;
- general rules with yield effects (e.g. cereal after cereal).

**Per year:**
1. **Return interval:** a gap below the minimum is a *problem* if ≤ half the minimum, otherwise a *caution*. Yield effect from the rule table (default −10 %).
2. **Family interval.**
3. **Pathogen pressure:** for each rotation-controllable soil- or residue-borne organism hosted by the crop:
   - *High* if a host grew last year, or ≥ 2 host years within the published break (`break_years`).
   - *Medium* if one host year falls within the break.
   - *Low* if hosts are older but within `survival_years`.
   - Yield effect −12 % (high) or −5 % (medium), weighted by severity. Only high-severity organisms at high pressure make a year a red "problem".
   - Excluded as not rotation-controllable: generalists (Rhizoctonia, Pythium, root-knot nematodes) and the migratory fall armyworm. Wireworms are handled by the cited "after grass/ley" rule.
   - Regional ranges: Striga (Africa/Asia), corn rootworm (North America/Europe), broomrape, cereal stem borers, black-grass.
   - **Cited sequence rules** (`applies_to` × `after` within `window_years`, e.g. continuous maize −13 %, legume before cereal +20 %, Striga trap crops +15 %) carry their published effect. The generic return-interval and predecessor-value effects (+15/+5/−5 %, Saxon yield classes) apply only when no cited rule matched, to avoid double counting.
   - Continuing perennial stands are not "crop after itself"; only stand age is checked.
4. **Predecessor effect:** +5 % after good predecessors or high-value preceding crops, −5 % after poor ones. Allelopathy notes.
5. **N carry-over:** the previous crop's residual N plus 50 % of the cover crop's fixation. Fertiliser saving is valued at $1.3/kg N.
6. **Simulation:** the season model over 15 seasons at the field (median and p10 yield, irrigation, ET, failure share), scaled by the rotation effect (clipped to −45…+15 %). Perennial establishment year at 70 %.
7. **Bare-soil days:** 365 − (crop season + cover-crop season). RUSLE soil loss uses the field's R·K·LS (from the terrain analysis of the drawn outline) times the crop's C (×0.6 with a cover crop).
8. **Water:** irrigation need vs. allocation; rain-fed failure share.
9. **Climate fit:** feasibility from frost share, complete seasons and yield level.

**Score** = priority-weighted mean of five 0–100 components (pests and diseases, soil, water, income, climate risk), minus 0.4 × (25 per problem, 10 per caution).

**Suggestions:** for every year that is not "good", the best single-crop replacement among climate-feasible crops, plus "add a cover crop" where the soil lies bare. Only gains are shown.

**Regional cropping systems** (temperate, irrigated arid, Mediterranean, tropical) limit the optimiser and the suggestions to crops grown in that kind of climate, plus the farmer's own crops. Plans that drop the farm's main (staple) crop entirely get a 15-point penalty.

**Optimiser:** beam search (width 24, at most 3 states per last crop) over climate-feasible candidates. A cover crop is added automatically after short-season crops, chosen so it shares no family or pathogen with the next cash crop. The **farm-type constraint**: perennial forage, vegetables and roots/tubers are only proposed if the farm already grows that kind of crop, because of markets, machinery and labour.

## 16. Accounts and sync
- E-mail + password accounts: scrypt (n = 2¹⁴, r = 8, p = 1) with a 16-byte salt; constant-time verification.
- Sessions are random 256-bit tokens stored as SHA-256 hashes, valid 90 days.
- Login is rate-limited (8 failures per 15 min per e-mail).
- Each account owns one farm document (fields, history, plans, settings), merged per field by `updated_at`.
- The account-free sync code remains for sharing a farm.

## <a id="rain-blend"></a>18. Rain: NASA POWER + GPM IMERG blend (`science/rainblend.py`, `engine/context.py`)
- **Inputs:** POWER `PRECTOTCORR` (MERRA-2, bias-corrected with gauges, ~50 km, local solar time) and GPM IMERG Final `IMERG_PRECTOT` (0.1°, UTC days, 1998 → ~2 months ago), both from the POWER point API.
- **Served rain** (only for |lat| ≤ 45°, the band covered by the gauge validation):
  - days with IMERG: R = 0.5·P + 0.5·I;
  - other days (before 1998, IMERG's ~2-month latency, the forecast bridge excluded): R = P · (0.5 + 0.5·r_m), where r_m = Σ I / Σ P for calendar month m over the overlap (capped 0.25–4). This "bridge" has the same long-run mean as the blend, so SPI/SPEI (which compare a window with the same window in every year since 1984) see one climatology and no jump at the 1998 or latency seams.
  - Poleward of 45° or when IMERG is unavailable: R = P (the card's Why says which).
- **Why a plain 50/50 mean?** The weight was fixed before the validation; 30 % and 70 % give similar results (V13), so it is not fitted to the 18 gauges. Averaging two partly independent estimates (reanalysis vs. satellite) cancels part of each one's random daily error: daily correlation with gauges rose at 16 of 18 sites. IMERG's gauge-calibrated monthly amounts pull POWER's bias down (mean |bias| 23.6 % → 17.9 %).
- **Used by:** the water balance (irrigation timing, rain-fed stress), SPI/SPEI, rotations and planner (climate normals, erosive rain). The Why steps and the source list credit GPM IMERG wherever it is used; `drought.rain_source` in the API reports the method and IMERG's last day.

## <a id="groundwater"></a>19. Regional water-storage trend from GRACE/GRACE-FO (`science/groundwater.py`, `data/grace.py`, `engine/water_supply.py`)
- **Input:** monthly JPL RL06.3 CRI mascon water-storage anomalies (cm of water) at the field's 0.5° cell, times the JPL land-hydrology scale factor; the nearest land cell within ~110 km for coastal fields.
- **Model:** y(t) = a + b·(t − t₀) + Σₖ₌₁,₂ [cₖ sin 2πkt + dₖ cos 2πkt] + e(t), fitted by least squares over all months up to the advice date (the GRACE → GRACE-FO gap is simply missing).
- **Significance:** monthly residuals are strongly autocorrelated (multi-year wet and dry spells), so the slope's standard error is inflated by √(n/n_eff) with n_eff = n(1 − ρ)/(1 + ρ), ρ the lag-1 residual autocorrelation (Santer et al., 2000); p from a t distribution with n_eff − 6 degrees of freedom. Typical n_eff is 8–25 for 261 months, which makes the test conservative.
- **Classes:** declining (b ≤ −0.3 cm/yr, p < 0.05), likely declining (p < 0.20), stable, likely rising, rising. 0.3 cm/yr (~1 cm in 3 years) is about the trend error from leakage and glacial-isostatic-adjustment models in mascon solutions, so smaller trends are never called a change.
- **Reported:** slope ± 95 % range, p, fitted change since 2003, the last 3 months' deseasonalised anomaly and its percentile, the last-5-years slope for context, and a chart of the monthly series with the fitted trend.
- **Decisions it drives:**
  - **Card** (irrigated fields, declining or likely declining): "Regional water reserves falling: −X cm since 2003" — prefer water-saving rotations and efficient irrigation, check the well. Risk moderate (significant) or low (likely). It is a planning card, not an irrigation instruction.
  - **Rotations:** for irrigated fields where storage is falling, the "water" priority in the ranking is multiplied by 1.5 (declining) or 1.25 (likely declining), and the response carries a `groundwater_note`.
  - **Drought status:** context only (see §3).
- **Caveats in every Why:** ~300 km footprint; total storage, not only groundwater; 2–3 month latency; a local well can disagree (V14 found exactly this at Fallon).

## 17. Recommendation engine (`engine/service.py`, `config/rules.yaml`)
Each module emits zero or more cards, each with risk, due date and a Why block (summary, steps with numbers, series, model, confidence, caveats, sources). Cards are ranked by risk, then due date. Thresholds are versioned in `rules.yaml`, and texts in six languages are in `messages.yaml`.

**Confidence** is a documented heuristic, not a calibrated probability:
- water balance 0.55, or 0.70 if the farmer entered their last irrigation;
- drought 0.6 with ≥ 3 indicators, else 0.45;
- regional water-storage trend 0.6 when significant (p < 0.05), else 0.45;
- disease 0.5; pests 0.55; NDVI 0.45; frost/heat 0.6;
- heat stress (people/livestock) 0.6, or 0.45 on the climatology fallback; solar pump 0.5; nearby fires 0.7 (0.5 on demo data); residue burning 0.55.

## <a id="rain-onset"></a>18. Rain-season onset, false starts and sowing windows (`science/onset.py`, `engine/rain_season.py`)
For rain-fed farmers in the tropics and monsoon regions, *when* to sow matters more than almost anything else. Sowing at the first shower risks losing seed and seedlings to a dry spell (a **false start**); sowing late shortens the season. Parameters live in `config/onset.yaml`; ADR-021 records the choices.

**Climatological seasons (both hemispheres, one or two per year).**
- The daily rain climatology (complete years since 1984, 31-day circular smoothing) is scanned for runs above the annual mean. This is where the anomalous accumulation rises, i.e. the climatological onset and cessation of Liebmann et al. (2012).
- Two rainy seasons are kept when the 2nd harmonic of the climatology is stronger than the 1st (Dunning, Black & Allan 2016), e.g. Machakos (ratio 1.5: MAM "long rains" and OND "short rains"). Otherwise the largest run is the one season.
- Seasons that cross New Year (southern hemisphere, e.g. Darwin NDJFMA) need no special case: each season instance is anchored at its climatological onset date in a given year.

**Per-year onset (Sivakumar 1988; Stern, Dennett & Garbutt 1981).** The first day of a 3-day period with ≥ 20 mm, starting with a wet day (≥ 1 mm), with no dry spell longer than 7 days in the following 30 days. The search runs from 45 days before to 60 days after the climatological onset (shorter when the season is short or the gap to the previous season is small). No valid onset in that window = a **failed season**.

**False start.** An *apparent* onset (the rain part of the criterion) followed by a dry spell > 7 days within 30 days. The site's false-start probability is the share of seasons whose first apparent onset was false.

**Cessation (Stern et al. 1981; Frère & Popov 1979, FAO).** A 100 mm soil store filled by rain and emptied by FAO-56 ET₀ (from NASA POWER). The season ends on the first day the store is empty, but not earlier than onset + 20 days or 3 weeks before the climatological end of the rains. This mirrors the fixed "earliest end date" of the Instat implementations. The 3-week offset was set on Machakos before any reference data were collected: an earliest end at mid-season piled the cessations onto that bound and gave median seasons of only 42–54 days. It was not fitted to the validation references. A store that runs dry is only taken as the end if no onset-sized rain (20 mm in 3 days) refills it within 21 days. Mid-season dry spells, common in semi-arid bimodal climates such as Machakos, otherwise ended the season too early; without this rule, the median Machakos OND end was 19 Dec instead of 3 Jan. The Sahel season-length check moved from MAE 12.7 to 12.5 days with the rule.

**Climatology product (`GET /api/rain-season`).** Per season:
- onset and cessation dates (p10–p90) and season length;
- false-start and failed-season percentages, and every year's onset, cessation and false starts;
- trends since 1984: Theil–Sen slope with Mann–Kendall p for onset, cessation and length, and false-start shares before vs. since 2005. These feed the "Field Shift" climate story, e.g. at Machakos the MAM season shortened by 6 days per decade (p = 0.07), and false starts rose from 15 % of years before 2005 to 40 % since.

**Live status ("this season" card, id `rain_onset`).** Observations, the Open-Meteo bridge and the 16-day forecast are scanned from the search window onwards. The phase is one of `before`, `not_started` (or late after the p80 onset), `forecast` (the rain criterion is met only in forecast days), `started`, `false_start`, `established` (30 days without a damaging spell), `ended` or `failed`.
- For `started`, the false-start risk is **conditional**: among all historical apparent onsets within ±20 days of this date's place in the season, the share followed by a damaging dry spell, given that none occurred in the days already checked (observed + forecast).
- The risk then sets the advice: below 20 %, sow now; 20–40 %, sow with care (moist to a hand's depth, keep seed to re-sow); 40 % or more, wait.

**Sowing windows per crop.** A crop must reach the end of its mid-season (grain fill; FAO-56 stage lengths) before the water-balance end of the season. The late (ripening) stage can run on stored water.
- `fit_pct`: share of past seasons in which sowing on the start date (onset, or expected median onset) would have achieved that.
- `sow_until`: last date that still works in 8 of 10 seasons.
- `max_variety_days`: the longest total cycle that fits in 8 of 10 seasons. When the field's crop does not fit, the card names an early variety (≤ N days) or a shorter crop.

**Where it is offered.** Rain-fed fields with |latitude| ≤ 35°, at least one rainy season and a real dry season: ≥ 60 days with climatological rain < ½ ET₀, the FAO agro-ecological-zones growing-period rule. Fallon, Córdoba and Ames therefore get no card; the API still returns the climatology with `applicable: false` and the reason.

**Planner.** For such fields, the planner's sowing-date scan is extended to cover the onset-based window. Every candidate gets `onset_ok`: on or after the median onset (rains have started in ≥ half of years) and no later than the latest sowing date. The recommended window is chosen only among `onset_ok` dates.

**Validation.** See [VALIDATION.md, V9](VALIDATION.md#v9).

## <a id="heat-stress"></a>19. Heat stress for people and livestock (`science/heatstress.py`, `engine/heat_cards.py`)
Card `heat_stress` (category `weather`). Applies to every field, whatever the crop or season, because people and animals work there every day.

**Hourly inputs** (`data/heatwx.py`): air temperature, relative humidity, 2 m wind and global horizontal irradiance (GHI). The chain degrades gracefully:
1. Forecast mode uses the Open-Meteo hourly forecast (T, RH, 10 m wind, GHI, direct radiation). The 10 m wind is converted to 2 m with FAO-56 eq. 47 (× 0.748).
2. Replay (as-of) mode uses NASA POWER hourly (`T2M`, `RH2M`, `WS2M`, `ALLSKY_SFC_SW_DWN`; MJ m⁻² h⁻¹ × 277.8 → W m⁻²).
3. Otherwise it uses the T/RH hours already in the field context, plus NASA POWER daily climatology (±7 days of year, last 10 years) for `WS2M` and `ALLSKY_SFC_SW_DWN`. The daily irradiation is spread over the day in proportion to cos θz. Confidence drops from 0.6 to 0.45, and a caveat says so.

**Outdoor WBGT** (ISO 7243:2017): WBGT = 0.7·T_nwb + 0.2·T_g + 0.1·T_a. The natural wet bulb T_nwb and the 150 mm black globe T_g are solved by fixed-point iteration from their steady-state energy balances, after **Liljegren et al. (2008)**:
- Globe: T_g⁴ = ½(ε_a T_a⁴ + ε_s T_s⁴) − h/(σ ε_g)(T_g − T_a) + S/(2σ ε_g)(1 − α_g)[f_dir(1/(2 cos θz) − 1) + 1 + α_s]. The convective coefficient h comes from the sphere Nusselt number Nu = 2 + 0.6 Re^½ Pr^⅓.
- Wick: T_nwb = T_a − (ΔH_vap/(c_p M_a/M_w))·(e_w − e_a)/(P − e_w)·(Pr/Sc)^0.56 + F_atm/h. Here F_atm is the long-wave and short-wave radiation absorbed by the wick, and h uses the cylinder correlation Nu = 0.281 Re^0.6 Pr^0.44.
- Supporting terms:
  - Saturation vapour pressure: Buck (1981).
  - Atmospheric emissivity: 0.575·e^0.143.
  - Direct-beam fraction: f_dir = exp(3 − 1.34 S* − 1.65/S*), where S* = GHI/TOA ≤ 0.85. When the forecast gives direct radiation, f_dir is taken from it instead.
  - Surface pressure: from elevation (FAO-56 eq. 7).
- Solar position: Spencer (1971) declination and equation of time. The hour-mean irradiance is evaluated at mid-hour.
- Wind floor: 0.5 m/s at 2 m. This follows KNMI/ECMWF operational practice (0.62 m/s at 10 m), because grid winds cannot resolve calm hours and the globe balance is ill-conditioned near calm (see VALIDATION V12).

**Work–rest limits:** NIOSH (2016) recommended limits, which equal the ISO 7243 Annex A reference values.
- Acclimatized: REL = 56.7 − 11.5·log₁₀M.
- Unacclimatized: RAL = 59.9 − 14.1·log₁₀M.
- M (W) follows ISO 8996: rest 115 W, moderate field work 300 W (REL 28.2 °C), heavy work 415 W (26.6 °C).
- The allowed work fraction f per hour is the largest f with WBGT ≤ REL(f·M_work + (1 − f)·M_rest), found by bisection.
- Risk levels: low if f = 1; moderate if f ≥ 0.75; high if 0.25 ≤ f < 0.75; severe if f < 0.25 (≈ the limit for near-rest).

**Card text:**
- **Days:** the first run of consecutive days with any restricted hour between 06:00 and 21:00.
- **Hours:** clock hours restricted at the run's worst level on at least half of those days.
- **Rest minutes:** (1 − f)·60 at the peak hour.
- **When f < 0.25:** the advice is to stop heavy work during those hours.

**Livestock THI**
- **Cattle and poultry:** THI = 0.8·T + RH·(T − 14.4) + 46.4. This is NRC (1971) in the °C form of Mader et al. (2006), with RH as a fraction.
  - Thresholds (St-Pierre et al. 2003): dairy cow 70, beef cow 75, laying hen 70, broiler 78.
  - Classes above the threshold (Hahn et al. 2009): alert +1…4, danger +5…9, emergency ≥ +10.
- **Sheep and goats:** THI = T − (0.31 − 0.31·RH)(T − 14.4) (Marai et al. 2007). Below 22.2 is no stress; 22.2–23.3 moderate; 23.3–25.6 severe; 25.6 and above extreme.
- **Card rule:** livestock alone raises a card only at *danger* or above (Marai's extreme class only). Mild alert is shown in the reasoning, not as a card. Card risk is danger → moderate, emergency → high.

## <a id="solar-pump"></a>20. Solar irrigation pump advisor (`science/solarpump.py`, `engine/solar_service.py`, `POST /api/solar-pump`)
- **Water need.** The FAO-56 Kc curve is piecewise linear over the crop's stages (ini, dev, mid, late). For perennials, the per-cutting curve is averaged over `season_days`. The curve is laid on a typical year from the planting date.
  - ETc = Kc × ET₀ uses the monthly mean FAO-56 PM ET₀ from NASA POWER for the last 20 complete years (observed days only).
  - Effective rain uses the USDA-SCS method from FAO CROPWAT (Smith 1992): P_eff = P(125 − 0.2P)/125 for P ≤ 250 mm/month, else 125 + 0.1P.
  - Net = ETc − P_eff. Gross = net / application efficiency (drip 0.90 … furrow 0.60). Daily volume V = gross (mm) × 10 × area (ha) per day.
- **Head.** H = (static lift [default 15 m] + operating pressure [drip 10, sprinkler 30, pivot 25, surface 1 m]) × 1.10 for pipe friction.
- **Hydraulic energy.** E_h = ρgHV/3.6·10⁶ = 0.002725·H·V kWh.
- **PV size** for each month: P_pv = E_h / (G · η_mp · PR).
  - G is the NASA POWER `ALLSKY_SFC_SW_DWN` monthly mean in kWh m⁻² d⁻¹ (= peak-sun hours).
  - η_mp = 0.45 is the motor-pump (wire-to-water) efficiency.
  - PR = [1 − 0.004 (T_cell − 25)] × 0.88, with T_cell = mean Tmax + 0.03·800 (Ross coefficient; Skoplaki & Palyvos 2009). The 0.88 covers soiling, wiring, mismatch and controller losses.
  - The **design month** is the month needing the largest array. This is normally the peak-need month, unless that month is unusually cloudy. Both months are reported.
  - Pump flow ≈ V / G (m³/h).
- **Economics** (indicative; the field's country, [§22](#country-economics); user values in the request override):
  - Solar: installed cost per kWp = 1,000 USD world small-system price × (0.65 + 0.35 × country price level / world median price level), annualised with CRF(8 %, 20 y) plus 2 %/yr O&M, divided by the season's pumped volume.
  - Diesel: L/m³ = 0.002725·H / (0.15 × 9.96 kWh/L), at the country's pump price (World Bank, latest reported year brought forward with the Brent crude cost per litre; else the sub-region median, else 1.10 USD/L) plus 25 % maintenance. The pump-set purchase is excluded, so the comparison is conservative for solar.
  - Costs are reported in USD and in the local currency (`*_local`, `currency`).
  - CO₂: 2.68 kg/L (IPCC 2006).
- **Card** `solar_pump`: category `planning`, risk `low`. It is shown only for irrigated fields.
- References: FAO & GIZ (2018); GIZ/FAO SPIS Toolbox; Kelley et al. (2010); IRENA (2016); Smith (1992).

## <a id="fires"></a>21. Active fires and residue burning (`data/firms.py`, `engine/fire_cards.py`)
**`fire_nearby`.** Uses NASA FIRMS active-fire detections within 50 km over the last 48 h (VIIRS 375 m, Schroeder et al. 2014; MODIS 1 km, Giglio et al. 2016). Low-confidence detections are dropped.
- Distance (haversine) and bearing (8-point compass) are given to the nearest fire.
- Risk: high if the nearest fire is ≤ 2 km; moderate if any fire is ≤ 10 km or there are ≥ 20 fires within 50 km (smoke); otherwise low.

**`residue_no_burn`.** Shown when all of these hold:
- the field is in a residue-burning region (`config/residue_burning.yaml`): NW and E Indo-Gangetic Plain, mainland South-East Asia, NE China plain;
- the crop is one that is burnt there;
- the date is in, or one month before, the burning months. Fires within 10 km also trigger it.

Quantities per hectare:
- residue = typical yield × residue-to-grain ratio (rice 1.2, wheat 1.3, maize 1.0; Jain et al. 2014);
- nutrient loss = residue × content × burn loss (N 90 %, P 25 %, K 20 %, S 50 %; Dobermann & Fairhurst 2002);
- C = residue × 0.40–0.43, of which 90 % is released (CO₂ = C × 44/12);
- soil-carbon gain when retained = 12 % of residue C in the first year (Powlson et al. 2008).

Recommended practice: Happy Seeder / Super Seeder direct sowing into the residue (Sidhu et al. 2015; most profitable option per Shyamsundar et al. 2019, *Science*), or chop-and-spread and incorporation.

## <a id="country-economics"></a>22. Country-specific prices, costs, currency, sowing dates and yield level (`science/economics.py`, ADR-027)
Every money value and every location default uses data for **the country the field is in**; a single U.S. or world number is used only as a labelled last fallback.
- **Country.** Offline 5 arc-min grid (~9 km) rasterised from Natural Earth 1:10m admin-0 (`config/country_grid_5mn.npz`, 111 KB, 252 countries/territories). A point on a water cell takes the nearest land cell within 2 cells. At sea → `fallback: true`.
- **Crop prices (USD/t).** FAOSTAT producer prices, mean of the latest 3 years ≥ 2017, per FieldShift crop (`config/economics.yaml` maps crops to FAOSTAT items; cotton: seed-cotton price ÷ 0.38 lint turnout). Countries that stopped reporting USD prices but still report the FAOSTAT producer price index (e.g. India after 2008) get the last local-currency price carried forward with that index and converted at the World Bank rate of the index year. Ladder: country → UN M49 sub-region median → world median → crop-table reference × the country's farm-price index (median ratio of its FAOSTAT prices to the world median, relative to the reference country). `price_scope` says which step was used.
- **Production costs (USD/ha).** No open dataset has per-crop costs for all countries, so they are modelled: cost = reference budget × intensity × (0.6 + 0.4 × price level). Intensity = the country's FAOSTAT national yield of the crop / the crop table's typical yield (clipped 0.1–1.3; else the country's median over crops): input use scales with the yield level achieved. Price level = World Bank PPP conversion factor ÷ market exchange rate (USA = 1), applied to the 40 % non-traded share (labour, services, land). Example: maize in Kenya ≈ 140 USD/ha instead of the 1,500 USD/ha U.S. budget.
- **Fertiliser N.** World Bank Pink Sheet urea (world market, latest annual average) ÷ 0.46 × 1.6 farm-gate mark-up (≈ 1.5 USD/kg N in 2025). No open country series exists, so this is the one input labelled `scope: "world"`.
- **Currency.** CLDR territory currency (Babel); World Bank official exchange rate (PA.NUS.FCRF, period average, latest year). Calculations and scores stay in USD; responses add `*_local` values and an `economics` block (country, currency, rate, year, source, per-crop price/cost scope and years, national FAOSTAT yield, yield-calibration factor). Without an exchange rate the amounts are shown in USD and the block says why.
- **Sowing dates.** Sacks et al. (2010) crop calendars: the field's 0.5° cell (or a neighbour), else the country median (`config/crop_calendar_30mn.npz`, 130 KB; `country_data.json`). They replace the generic temperate default calendar. The field-weather rules (tropical rainy-season onset, Mediterranean winter-rain calendar; ADR-021) are kept where they apply: they come from the field's own rainfall, while many tropical Sacks entries are national-level. The observed season length (harvest − sowing) sets the thermal-time target when it is within 0.5–1.15 × the FAO-56 season; otherwise the FAO-56 length is used (calendar cells can mix crop types). Without this, a late local sowing (Córdoba wheat, 28 Nov) was stretched over the 240-day FAO-56 season into August.
- **Yield level.** On top of the crop × macro-region calibration (§2, ADR-022), a country factor (`config/yield_country_factors.yaml`): the mean residual of the 41 benchmarked countries (V10), shrunk n/(n+2), clipped 0.5–2; for 150 other countries half the median log ratio of their FAOSTAT yields to their macro region's median, shrunk n/(n+2), clipped 0.67–1.5 (half, because part of a national difference is climate, already simulated).
- **Rebuild.** `scripts/build_country_data.py download|build|yieldcal` (data box; ≈ 30 MB of downloads, < 1 min to build).

## Optional LLM phrasing layer
Behind the flag `FIELDSHIFT_LLM_EXPLAIN` (off by default; not required). It is not implemented in v1; see ROADMAP.md. All texts are template-generated from computed numbers, so nothing is invented.

## References
- Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998) *Crop evapotranspiration*, FAO Irrigation and Drainage Paper 56.
- Doorenbos, J., Kassam, A.H. (1979) *Yield response to water*, FAO Irrigation and Drainage Paper 33.
- Steduto, P. et al. (2009) AquaCrop — the FAO crop model. *Agronomy Journal* 101: 426–437.
- McKee, T.B., Doesken, N.J., Kleist, J. (1993) The relationship of drought frequency and duration to time scales. 8th Conf. Applied Climatology.
- Vicente-Serrano, S.M. et al. (2010) A multiscalar drought index sensitive to global warming: SPEI. *J. Climate* 23: 1696–1718.
- Svoboda, M. et al. (2002) The Drought Monitor. *BAMS* 83: 1181–1190.
- AHDB (2017) Hutton criteria for potato late blight.
- Sentelhas, P.C. et al. (2008) Suitability of relative humidity as an estimator of leaf wetness duration. *Agric. For. Meteorol.* 148: 392–400.
- de Vallavieille-Pope, C. et al. (1995) Comparative effects of temperature and interrupted wet periods on germination, penetration, and infection of *Puccinia recondita* and *P. striiformis*. *Phytopathology* 85: 409–415.
- Gubler, W.D. et al. (1999) Control of powdery mildew using the UC Davis powdery mildew risk index. APSnet.
- McMaster, G.S., Wilhelm, W.W. (1997) Growing degree-days: one equation, two interpretations. *Agric. For. Meteorol.* 87: 291–300.
- Sen, P.K. (1968) Estimates of the regression coefficient based on Kendall's tau. *JASA* 63: 1379–1389.
- Fry, W.E. et al. (2013) The 2009 late blight pandemic in the eastern United States. *Plant Disease* 97: 296–306.
- Sivakumar, M.V.K. (1988) Predicting rainy season potential from the onset of rains in Southern Sahelian and Sudanian climatic zones of West Africa. *Agric. For. Meteorol.* 42: 295–305.
- Stern, R.D., Dennett, M.D., Garbutt, D.J. (1981) The start of the rains in West Africa. *J. Climatology* 1: 59–68.
- Frère, M., Popov, G.F. (1979) *Agrometeorological crop monitoring and forecasting*. FAO Plant Production and Protection Paper 17.
- Liebmann, B. et al. (2012) Seasonality of African precipitation from 1996 to 2009. *J. Climate* 25: 4304–4322.
- Dunning, C.M., Black, E.C.L., Allan, R.P. (2016) The onset and cessation of seasonal rainfall over Africa. *J. Geophys. Res. Atmos.* 121: 11405–11424.
- FAO (1978) Report on the Agro-ecological Zones Project, Vol. 1: Methodology and results for Africa. World Soil Resources Report 48.

- Liljegren, J.C., Carhart, R.A., Lawday, P., Tschopp, S., Sharp, R. (2008) Modeling the wet bulb globe temperature using standard meteorological measurements. *J. Occup. Environ. Hyg.* 5: 645–655. doi:10.1080/15459620802310770.
- ISO 7243:2017 Ergonomics of the thermal environment — Assessment of heat stress using the WBGT index. ISO 8996:2021 Determination of metabolic rate.
- NIOSH (2016) Criteria for a recommended standard: occupational exposure to heat and hot environments. DHHS (NIOSH) Pub. 2016-106.
- Stull, R. (2011) Wet-bulb temperature from relative humidity and air temperature. *J. Appl. Meteor. Climatol.* 50: 2267–2269.
- Buck, A.L. (1981) New equations for computing vapor pressure and enhancement factor. *J. Appl. Meteor.* 20: 1527–1532.
- Mader, T.L., Davis, M.S., Brown-Brandl, T. (2006) Environmental factors influencing heat stress in feedlot cattle. *J. Anim. Sci.* 84: 712–719.
- St-Pierre, N.R., Cobanov, B., Schnitkey, G. (2003) Economic losses from heat stress by US livestock industries. *J. Dairy Sci.* 86 (E. Suppl.): E52–E77.
- Hahn, G.L., Gaughan, J.B., Mader, T.L., Eigenberg, R.A. (2009) Thermal indices and their applications for livestock environments. In: *Livestock Energetics and Thermal Environmental Management*, ASABE, 113–130.
- Marai, I.F.M., El-Darawany, A.A., Fadiel, A., Abdel-Hafez, M.A.M. (2007) Physiological traits as affected by heat stress in sheep — a review. *Small Rumin. Res.* 71: 1–12.
- FAO & GIZ (2018) *The benefits and risks of solar-powered irrigation — a global overview*. Rome.
- Kelley, L.C., Gilbertson, E., Sheikh, A., Eppinger, S.D., Dubowsky, S. (2010) On the feasibility of solar-powered irrigation. *Renew. Sustain. Energy Rev.* 14: 2669–2682.
- Skoplaki, E., Palyvos, J.A. (2009) Operating temperature of photovoltaic modules: a survey of pertinent correlations. *Solar Energy* 83: 614–624.
- Smith, M. (1992) CROPWAT, FAO Irrigation and Drainage Paper 46.
- Schroeder, W., Oliva, P., Giglio, L., Csiszar, I.A. (2014) The New VIIRS 375 m active fire detection data product. *Remote Sens. Environ.* 143: 85–96.
- Giglio, L., Schroeder, W., Justice, C.O. (2016) The collection 6 MODIS active fire detection algorithm and fire products. *Remote Sens. Environ.* 178: 31–41.
- Dobermann, A., Fairhurst, T.H. (2002) Rice straw management. *Better Crops International* 16 (Special Suppl.): 7–11.
- Jain, N., Bhatia, A., Pathak, H. (2014) Emission of air pollutants from crop residue burning in India. *Aerosol Air Qual. Res.* 14: 422–430.
- Powlson, D.S. et al. (2008) Carbon sequestration in European soils through straw incorporation: limitations and alternatives. *Waste Manag.* 28: 741–746.
- Sidhu, H.S. et al. (2015) Development and evaluation of the Turbo Happy Seeder for sowing wheat into heavy rice residues in NW India. *Field Crops Res.* 184: 201–212.
- Shyamsundar, P. et al. (2019) Fields on fire: alternatives to crop residue burning in India. *Science* 365: 536–538.
- Huffman, G.J. et al. (2023) NASA Global Precipitation Measurement (GPM) Integrated Multi-satellitE Retrievals for GPM (IMERG), Algorithm Theoretical Basis Document, Version 07. NASA GSFC.
- Gupta, H.V. et al. (2009) Decomposition of the mean squared error and NSE performance criteria (KGE). *J. Hydrology* 377: 80–91.
- Watkins, M.M. et al. (2015) Improved methods for observing Earth's time variable mass distribution with GRACE using spherical cap mascons. *JGR Solid Earth* 120: 2648–2671.
- Wiese, D.N., Landerer, F.W., Watkins, M.M. (2016) Quantifying and reducing leakage errors in the JPL RL05M GRACE mascon solution. *Water Resources Research* 52: 7490–7502.
- Santer, B.D. et al. (2000) Statistical significance of trends and trend differences in layer-average atmospheric temperature time series. *JGR* 105: 7337–7356.
- Rodell, M., Velicogna, I., Famiglietti, J.S. (2009) Satellite-based estimates of groundwater depletion in India. *Nature* 460: 999–1002.
- Rodell, M. et al. (2018) Emerging trends in global freshwater availability. *Nature* 557: 651–659.
