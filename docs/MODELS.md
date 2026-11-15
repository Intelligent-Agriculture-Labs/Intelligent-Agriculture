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

**Root-zone water balance** (eq. 85), daily: Dᵣ,ᵢ = Dᵣ,ᵢ₋₁ − Pᵢ − Iᵢ + ETc,adj,ᵢ + DPᵢ.
- TAW = θ-range × Zᵣ. θ-range by texture class (Table 19 mid-points); Zᵣ grows from Zmin to Zmax by the end of the development stage.
- RAW = p·TAW, with p adjusted by p + 0.04(5 − ETc) (Table 22 note).
- Kₛ = (TAW − Dᵣ)/((1 − p) TAW) when Dᵣ > RAW (eq. 84). ETc,adj = Kₛ·Kc·ET₀. Overflow becomes deep percolation.
- Mass closure is unit-tested.

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

**Assimilation hook.** `simulate(..., assimilate={date: Dᵣ_obs}, assimilation_weight=α)` nudges the state with Dᵣ ← (1 − α) Dᵣ + α Dᵣ_obs. It is used in the experiments with ERA5-Land; it is not on by default (EXPERIMENTS.md explains why).

## <a id="drought"></a>3. Drought (`drought.py`)
- **SPI-n** (McKee et al., 1993; WMO-No. 1090): n-day rain sums compared with the same calendar window (±7 days) in every year since 1984. Gamma fit (scipy, location fixed at 0), mixed with the probability of zero, then transformed to a normal quantile.
- **SPEI-n** (Vicente-Serrano et al., 2010): the same for P − ET₀, using empirical plotting positions.
- **Percentiles:** SMAP surface soil moisture against its own record; vegetation condition index VCI = (NDVI − NDVImin)/(NDVImax − NDVImin) per 16-day period since 2001.
- **Status:** a weighted blend of indicator levels, following the USDM-style convergence of evidence.
  - SPI thresholds: D0 ≤ −0.5, D1 ≤ −0.8, D2 ≤ −1.3, D3 ≤ −1.6, D4 ≤ −2.0.
  - Weights: SPI-90 0.30, SPEI-90 0.25, SPI-30 0.15, soil-moisture percentile 0.20, VHI 0.10, plus the long-term SPEI-12 at 0.30 (EXP-03).

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

Texts are in `config/pest_disease.yaml` in six languages. Actions are scouting and cultural control; treatment decisions are referred to local thresholds and extension services, and no product is ever named. Validation is in [VALIDATION.md V9](VALIDATION.md).

**Leaf wetness (shared).**
- **Default:** an hour is wet when RH ≥ 90 %, or when rain ≥ 0.1 mm falls in that hour. RH ≥ 90 % performed best overall against sensors in Brazil, Canada, Italy and the U.S. (fraction correct 0.87–0.92; Sentelhas et al. 2008).
- **Alternative:** dew-point depression with hysteresis: wet from T − Td ≤ 1.8 °C until T − Td ≥ 2.2 °C (Rao et al. 1998, as tested by Sentelhas et al. 2008).
- **Missing dew point:** derived from T and RH with the Magnus formula (Alduchov & Eskridge 1996).
- **Wet periods:** runs of wet hours. Dry gaps up to a pathogen-specific length (Magarey's D50 classes) do not end a period. A period counts on every calendar day it covers.

**Generic infection equation** (Magarey, Sutton & Thayer 2005, eqs. 1–2), used for the fungal leaf diseases:

  f(T) = ((Tmax − T)/(Tmax − Topt)) · ((T − Tmin)/(Topt − Tmin))^((Topt − Tmin)/(Tmax − Topt)), with T the mean temperature of the wet period
  W(T) = Wmin / f(T), with no infection if W(T) > Wmax
  score = min(1, wet hours / W(T)), taking the best wet period that starts on each day

| Model | Hosts in FieldShift | Range | Criteria / parameters | Source |
|---|---|---|---|---|
| Rice blast (*Magnaporthe oryzae*) | rice | everywhere rice grows | **BLASTAM:** wet period mean 15–25 °C; wet hours ≥ 17/15/14/13/12/11/11/10 h at 15/16/17/18/19/20/21/22–25 °C; mean of the 5 daily means up to that day 20–25 °C → favourable (1.0). ≥ 10 h with one temperature condition missed → quasi-favourable (0.5). Temperatures fine but too short → 0.5·h/required. Symptoms follow 7–10 d later. | BLASTAM sheets of the Ibaraki and Hiroshima prefectural plant protection offices (table after Yokouchi, Higuchi & Munakata) |
| Wheat leaf rust (*Puccinia triticina*) | winter/spring/durum wheat, triticale, spelt | worldwide | Magarey: Tmin 2.6, Topt 25, Tmax 30 °C; Wmin 5 h, Wmax 16 h; dry gaps > 1 h end a period (D50 "sensitive") | Magarey et al. 2005, Table 2 (*P. recondita*); Roelfs et al. 1992 |
| Wheat stem rust (*P. graminis* f. sp. *tritici*) | wheats, triticale, spelt, barley | worldwide | Magarey: Tmin 2, Topt 18, Tmax 30 °C (germination 2/15–24/30 °C; maximum infection at 18 °C); Wmin 6 h (6–8 h dew needed); Wmax = 3.8 + 3.0·Wmin = 21.8 h (Magarey's regression). The light requirement after dew is not modelled. | Roelfs, Singh & Saari 1992 (CIMMYT), Table 2 and text |
| Late blight, tropical (*Phytophthora infestans*) | potato, tomato | \|lat\| < 23.44° (Hutton is used outside the tropics) | **Wallin severity value** per day, from the longest RH ≥ 90 % period and its mean T. 7.2–11.6 °C: 16/19/22/25 h → SV 1/2/3/4. 11.7–15.0 °C: 13/16/19/22 h. 15.1–26.6 °C: 10/13/16/19 h. Outside 7.2–26.6 °C → 0. Score = SV/4. The 7-day SV sum is shown as evidence. | Wallin 1962; BLITECAST (Krause et al. 1975); Grünwald et al. 2000 for Toluca |
| Maize gray leaf spot (*Cercospora zeae-maydis*) | maize, silage maize, sweet corn | worldwide; 30–120 days after planting | Index of the two best weather predictors over V4–V12: hours at 22–30 °C (observed 85.5–230.5 h) and night hours (20–08 h) with RH ≥ 90 % (122–330 h). Trailing 14-day totals are scaled to the upper end of each range, pro-rated from 30 days: score = ½ (warm/107.6 h + humid nights/154 h), each capped at 1. This is a risk *index*, not the authors' fitted regression. | Paul & Munkvold 2005 |
| Coffee leaf rust (*Hemileia vastatrix*) | coffee *(not yet a FieldShift crop)* | tropics | Magarey: Tmin 12.5, Topt 23, Tmax 32.5 °C (cardinal temperatures of the Kushalappa & Eskes curve; optimum within the 21–25 °C germination optimum); Wmin 6 h (wetness curve zero point); Wmax 21.8 h; dry gap ≤ 2 h. Score ×0.5 on days with Tmax outside 22–28 °C, the band linked to the 2008–2013 epidemics. | Kushalappa & Eskes 1989; Avelino et al. 2015 |
| Black Sigatoka (*Pseudocercospora fijiensis*) | banana *(not yet a FieldShift crop)* | tropics | Magarey: Tmin 20, Topt 26.5, Tmax 35 °C (germination); Wmin 12 h (**assumption** within the 0–18 h range reported); Wmax 48 h; dry gap ≤ 2 h. | Jacome, Schuh & Stevenson 1991; Jacome & Schuh 1992 |
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
Candidates are the farmer's current rotation plus ten templates (`config/rotations.yaml`). Each slot is simulated over the last 15 seasons with the farmer's irrigation method, strategy and allocation. Planting dates are hemisphere- and tropics-aware: in the tropics, planting starts with the wettest 4-month window.

**Feasibility filter.** A strategy is dropped if any slot:
- has < 60 % valid seasons;
- has frost during the season in > 30 % of years; or
- has a median yield < 35 % of typical (too cold, short or dry).

**Metrics.**
- **Water:** mean gross irrigation (irrigated) or ETₘ − ETₐ shortfall (rain-fed), mm/yr. Scored relative to the other candidates (lower is better).
- **Income:** mean gross margin = yield × price − cost + 40 kg N/ha × $1.3 after a legume. Rotation effects:
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

## <a id="field-detect"></a>11. Tap-to-detect field boundaries (`science/fielddetect.py`)
The farmer taps inside a field, and an editable polygon comes back in ~0.5–3 s.

**Imagery.** Sub-metre RGB (Esri World Imagery; USDA NAIP option in the U.S.), a 3 × 3 tile window at zoom 17, retrying at zoom 16 if the field touches the window edge.

**Pipeline:**
1. Downsample to ~2.7 m and apply a 5 × 5 median filter, which removes crop rows and wheel tracks.
2. Convert to CIE-Lab.
3. Felzenszwalb–Huttenlocher graph segmentation (scale 300).
4. Snap the tap to the lowest-gradient pixel nearby.
5. Edge-aware region growing over adjacent segments. A segment joins when ΔE(segment, region mean) < 9 **and** the median gradient along the shared border is below max(90th-percentile gradient, 5). Roads and ditches stop the growth; internal irrigation borders do not.
6. Fill holes, morphological opening, keep the component containing the tap.
7. Trace the contour and simplify it (Douglas–Peucker, 2 px).

**Confidence** = f(boundary contrast, compactness, border contact).

**Visual check on real farms:**
- Fallon border-irrigated field and Córdoba wheat field: outlined correctly.
- Iowa: correct, with one leak through a farmstead gap.
- Terraced smallholder plots (Machakos): only one strip is found.

That is why the polygon always stays editable.

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

## 17. Recommendation engine (`engine/service.py`, `config/rules.yaml`)
Each module emits zero or more cards, each with risk, due date and a Why block (summary, steps with numbers, series, model, confidence, caveats, sources). Cards are ranked by risk, then due date. Thresholds are versioned in `rules.yaml`, and texts in six languages are in `messages.yaml`.

**Confidence** is a documented heuristic, not a calibrated probability:
- water balance 0.55, or 0.70 if the farmer entered their last irrigation;
- drought 0.6 with ≥ 3 indicators, else 0.45;
- disease 0.5; pests 0.55; NDVI 0.45; frost/heat 0.6.

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
