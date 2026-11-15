"""Solar photovoltaic (PV) irrigation pump sizing — pure physics, no I/O.

Hydraulic energy to lift V m³ of water through a total dynamic head H m:
    E_h [kWh] = ρ · g · H · V / 3.6e6 = 0.002725 · H · V          (ρ = 1000 kg/m³, g = 9.81 m/s²)
PV array peak power needed in a month with daily irradiation G [kWh m⁻² d⁻¹ = "peak sun hours"]:
    P_pv [kWp] = E_h,day / (G · η_mp · PR)
where η_mp is the motor-pump subsystem efficiency (wire-to-water) and PR the PV performance ratio
(temperature, soiling, wiring, mismatch and controller losses). Standard method in
  * FAO & GIZ (2018) The benefits and risks of solar-powered irrigation – a global overview, Rome;
  * GIZ/FAO SPIS Toolbox (2017/2020), module "Design" (pump sizing worksheet);
  * Kelley, Gilbertson, Sheikh, Eppinger & Dubowsky (2010), On the feasibility of solar-powered
    irrigation, Renew. Sustain. Energy Rev. 14:2669–2682, doi:10.1016/j.rser.2010.07.061.
PV module temperature loss: P(Tc)/P(25 °C) = 1 + γ (Tc − 25), γ ≈ −0.004 K⁻¹ (crystalline Si),
Tc = Ta + k·G_poa with Ross coefficient k ≈ 0.03 K m² W⁻¹ (Skoplaki & Palyvos 2009, Sol. Energy 83:614).
Effective rainfall (USDA-SCS method as in FAO CROPWAT, Smith 1992):
    P_eff = P (125 − 0.2 P)/125  for P ≤ 250 mm/month,  else 125 + 0.1 P.
Diesel: fuel L = E_h / (η_diesel · LHV), LHV ≈ 9.96 kWh/L (35.9 MJ/L); CO₂ 2.68 kg/L (IPCC 2006
Guidelines vol. 2 ch. 3: 74.1 t CO₂/TJ × 0.0359 TJ/kL ≈ 2.66–2.68).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass

RHO_G_KWH = 1000.0 * 9.81 / 3.6e6  # kWh per m³ per m of head = 0.002725
DIESEL_LHV_KWH_L = 9.96
DIESEL_CO2_KG_L = 2.68


def hydraulic_kwh(volume_m3: float, head_m: float) -> float:
    return RHO_G_KWH * head_m * volume_m3


def effective_rain_mm(p_month_mm: float) -> float:
    p = max(0.0, p_month_mm)
    return p * (125.0 - 0.2 * p) / 125.0 if p <= 250.0 else 125.0 + 0.1 * p


def pv_temperature_factor(
    t_air_c: float, gamma: float = -0.004, ross_k: float = 0.03, g_wm2: float = 800.0
) -> float:
    tc = t_air_c + ross_k * g_wm2
    return min(1.0, 1.0 + gamma * (tc - 25.0))


def pv_kwp(e_hyd_kwh_day: float, psh_kwh_m2_day: float, eta_mp: float, pr: float) -> float:
    if psh_kwh_m2_day <= 0:
        return float("inf")
    return e_hyd_kwh_day / (psh_kwh_m2_day * eta_mp * pr)


def crf(rate: float, years: int) -> float:
    """Capital recovery factor."""
    if rate == 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


@dataclass
class Month:
    month: int
    et0_mm_day: float
    kc: float
    rain_mm: float
    peff_mm: float
    net_mm: float  # net irrigation need (month)
    gross_mm: float
    volume_m3_day: float
    e_hyd_kwh_day: float
    psh: float  # kWh m-2 d-1 (NASA POWER ALLSKY_SFC_SW_DWN)
    t_air_c: float
    pr: float
    kwp_needed: float


@dataclass
class Design:
    months: list[Month]
    design_month: int
    peak_need_month: int
    kwp: float
    flow_m3_h: float
    head_m: float
    area_ha: float
    annual_m3: float
    annual_hyd_kwh: float
    annual_pv_kwh: float
    hyd_kwh_m3: float
    pv_kwh_m3: float
    solar_capex_usd: float
    solar_usd_m3: float
    diesel_l_m3: float
    diesel_usd_m3: float
    diesel_l_year: float
    co2_t_year: float


def size_system(
    months: list[tuple[int, float, float, float, float, float]],
    area_ha: float,
    head_m: float,
    efficiency: float,
    *,
    eta_mp: float = 0.45,
    other_losses: float = 0.88,
    capex_usd_kwp: float = 1000.0,
    om_frac: float = 0.02,
    lifetime_y: int = 20,
    discount: float = 0.08,
    diesel_eta: float = 0.15,
    diesel_price_usd_l: float = 1.1,
    diesel_om_frac: float = 0.25,
) -> Design:
    """months: (month, ET0 mm/day, Kc, rain mm/month, PSH kWh/m²/day, mean Tmax °C), season months only.
    The design month is the month needing the largest PV array (water need ÷ sunshine), which is the
    month of peak water need unless that month is unusually cloudy."""
    rows: list[Month] = []
    for m, et0, kc, rain, psh, tmax in months:
        nd = calendar.monthrange(2001, m)[1]
        etc = kc * et0 * nd
        peff = min(effective_rain_mm(rain), etc)
        net = max(0.0, etc - peff)
        gross = net / max(efficiency, 0.3)
        vol = gross / nd * 10.0 * area_ha  # 1 mm on 1 ha = 10 m³
        eh = hydraulic_kwh(vol, head_m)
        pr = pv_temperature_factor(tmax) * other_losses
        rows.append(
            Month(m, et0, kc, rain, peff, net, gross, vol, eh, psh, tmax, pr, pv_kwp(eh, psh, eta_mp, pr))
        )
    if not rows:
        raise ValueError("no season months")
    dm = max(rows, key=lambda r: r.kwp_needed)
    pk = max(rows, key=lambda r: r.volume_m3_day)
    kwp = dm.kwp_needed
    flow = dm.volume_m3_day / dm.psh if dm.psh > 0 else 0.0  # pump rating ≈ daily volume over peak-sun hours
    annual_m3 = sum(r.volume_m3_day * calendar.monthrange(2001, r.month)[1] for r in rows)
    annual_hyd = hydraulic_kwh(annual_m3, head_m)
    annual_pv = annual_hyd / eta_mp  # PV energy actually used for pumping
    capex = kwp * capex_usd_kwp
    annual_cost = capex * crf(discount, lifetime_y) + capex * om_frac
    solar_m3 = annual_cost / annual_m3 if annual_m3 > 0 else float("nan")
    l_m3 = RHO_G_KWH * head_m / (diesel_eta * DIESEL_LHV_KWH_L)
    diesel_m3 = l_m3 * diesel_price_usd_l * (1 + diesel_om_frac)
    l_year = l_m3 * annual_m3
    return Design(
        rows,
        dm.month,
        pk.month,
        kwp,
        flow,
        head_m,
        area_ha,
        annual_m3,
        annual_hyd,
        annual_pv,
        RHO_G_KWH * head_m,
        RHO_G_KWH * head_m / eta_mp,
        capex,
        solar_m3,
        l_m3,
        diesel_m3,
        l_year,
        l_year * DIESEL_CO2_KG_L / 1000.0,
    )
