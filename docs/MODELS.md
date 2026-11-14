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
| Fall armyworm | 10.9 / 35 | 350 per generation | Hogg et al., 1982 |

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

## 9. Recommendation engine (`engine/service.py`, `config/rules.yaml`)
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
