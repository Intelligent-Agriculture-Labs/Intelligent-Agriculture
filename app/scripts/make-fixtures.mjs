// Generates MOCK_*.json fixtures (synthetic, NOT real data) used only when the API is unreachable
// and no device cache exists. The UI always shows a red "MOCK DATA" banner for these.
// Run: node scripts/make-fixtures.mjs
import { writeFileSync } from "node:fs";

const dir = "src/api/__fixtures__/";
const W = (name, obj) => writeFileSync(dir + name, JSON.stringify(obj, null, 1));
const MOCK = "MOCK — synthetic placeholder, not NASA data";

const day = (d0, i) => {
  const d = new Date(d0);
  d.setUTCDate(d.getUTCDate() + i);
  return d.toISOString().slice(0, 10);
};
const wave = (n, base, amp, phase = 0, noise = 0.15) =>
  Array.from({ length: n }, (_, i) => base + amp * Math.sin((i / n) * Math.PI * 2 + phase) + amp * noise * Math.sin(i * 1.7));

const crops = [
  ["alfalfa", "Alfalfa", "Fabaceae", "perennial", true, 1.5, 365, 16, "leaf"],
  ["maize", "Maize (grain)", "Poaceae", "annual", false, 1.2, 140, 11, "nutrition"],
  ["maize_silage", "Maize (silage)", "Poaceae", "annual", false, 1.2, 120, 50, "nutrition"],
  ["winter_wheat", "Winter wheat", "Poaceae", "annual", false, 1.2, 270, 6, "nutrition-outline"],
  ["barley", "Barley", "Poaceae", "annual", false, 1.0, 120, 5, "nutrition-outline"],
  ["sorghum", "Sorghum", "Poaceae", "annual", false, 1.4, 120, 6, "nutrition"],
  ["teff", "Teff (forage)", "Poaceae", "annual", false, 0.6, 90, 9, "flower-outline"],
  ["safflower", "Safflower", "Asteraceae", "annual", false, 1.8, 140, 2.5, "flower"],
  ["dry_bean", "Dry bean", "Fabaceae", "annual", true, 0.8, 100, 2.5, "ellipse"],
  ["potato", "Potato", "Solanaceae", "annual", false, 0.5, 130, 45, "egg"],
  ["cover_rye_vetch", "Cover: rye + vetch", "Mixed", "cover", true, 1.0, 180, 0, "leaf-outline"],
];
W(
  "MOCK_crops.json",
  crops.map(([id, name, family, type, n_fixing, root_depth_m, season_days, typical_yield_t_ha, icon]) => ({
    id,
    name,
    family,
    type,
    n_fixing,
    root_depth_m,
    season_days,
    typical_yield_t_ha,
    icon,
  })),
);

W("MOCK_presets.json", [
  {
    id: "fallon_nv",
    name: "Fallon, Nevada (USA) — alfalfa",
    lat: 39.4735,
    lon: -118.7774,
    crop: "alfalfa",
    planting_date: "2026-03-20",
    irrigation: "flood",
    current_rotation: ["alfalfa", "alfalfa", "alfalfa", "alfalfa", "alfalfa"],
    story: "MOCK: Lahontan Valley alfalfa grower facing reduced irrigation allocations.",
    cached: false,
  },
  {
    id: "machakos_ke",
    name: "Machakos (Kenya) — maize smallholder",
    lat: -1.5177,
    lon: 37.2634,
    crop: "maize",
    planting_date: "2026-10-20",
    irrigation: "none",
    current_rotation: ["maize", "maize", "maize"],
    story: "MOCK: rain-fed smallholder in a semi-arid bimodal-rainfall region.",
    cached: false,
  },
]);

const n = 60;
const d0 = "2026-09-16";
const mk = (id, label, unit, vals, source, normal) => ({
  id,
  label,
  unit,
  source,
  kind: "observed",
  points: vals.map((v, i) => ({ date: day(d0, i), value: Math.round(v * 100) / 100 })),
  normal: normal ? normal.map((v, i) => ({ date: day(d0, i), value: Math.round(v * 100) / 100 })) : undefined,
});
const series = [
  mk("et0", "Reference ET₀", "mm/day", wave(n, 4.2, 1.8, 1), "nasa_power", wave(n, 4.0, 1.6, 1, 0)),
  mk(
    "precip",
    "Rain",
    "mm",
    Array.from({ length: n }, (_, i) => (i % 13 === 0 ? 6 : i % 7 === 0 ? 1.5 : 0)),
    "nasa_power",
  ),
  mk("soil_depletion", "Root-zone depletion", "mm", wave(n, 70, 30, 0.3), "fieldshift_model"),
  mk("smap_sm", "SMAP soil moisture", "m³/m³", wave(n, 0.14, 0.04, 2), "smap_l3e", wave(n, 0.18, 0.03, 2, 0)),
  mk("ndvi", "NDVI", "", wave(n, 0.55, 0.15, 0.5), "modis_ndvi", wave(n, 0.62, 0.12, 0.5, 0)),
  mk("tmax", "Max temperature", "°C", wave(n, 24, 7, 1.2), "nasa_power", wave(n, 22, 7, 1.2, 0)),
];
const src = (id, name, provider, resolution, latency, is_nasa = true) => ({
  id,
  name,
  provider,
  url: "https://example.invalid/mock",
  resolution,
  latency,
  last_date: "2026-11-12",
  is_nasa,
  status: "demo",
});
const sources = [
  src("nasa_power", "NASA POWER daily agroclimatology", "NASA LaRC", "0.5° × 0.625°", "~2 days"),
  src("smap_l3e", "SMAP L3 enhanced soil moisture", "NASA/ORNL DAAC", "9 km", "~2 days"),
  src("modis_ndvi", "MODIS MOD13Q1 NDVI", "NASA/ORNL DAAC", "250 m", "~16 days"),
  src("openmeteo_forecast", "16-day forecast", "Open-Meteo", "~11 km", "hourly", false),
];
const why = (summary, s, conf) => ({
  summary: `${MOCK}. ${summary}`,
  steps: ["MOCK step 1: placeholder reasoning", "MOCK step 2: placeholder reasoning"],
  series: s,
  model: "MOCK model",
  model_doc: "water-balance",
  confidence: conf,
  confidence_note: "MOCK confidence",
  caveats: ["MOCK: SMAP pixel is 9 km; your field is much smaller."],
  sources: ["nasa_power", "smap_l3e"],
});
W("MOCK_advice.json", {
  field: {
    lat: 39.4735,
    lon: -118.7774,
    crop: "alfalfa",
    planting_date: "2026-03-20",
    irrigation: "flood",
    elevation_m: 1203,
    slope_pct: 0.4,
    area_ha: null,
    soil: { texture: "silt loam", clay_pct: 18, sand_pct: 30, soc_g_kg: 8, taw_mm_per_m: 160, source: "soilgrids" },
  },
  generated_at: "2026-11-14T12:00:00Z",
  as_of: "2026-11-14",
  cards: [
    {
      id: "irrigate",
      category: "water",
      priority: 1,
      risk: "high",
      icon: "water",
      title: "MOCK: Irrigate 22 mm before Thursday",
      detail: "Root zone is 74% depleted.",
      due: "2026-11-19",
      amount: { value: 22, unit: "mm" },
      why: why("Water.", ["soil_depletion", "et0", "precip"], 0.7),
    },
    {
      id: "disease_rust",
      category: "disease",
      priority: 2,
      risk: "moderate",
      icon: "bug",
      title: "MOCK: Moderate rust risk from Wednesday",
      detail: "Humid nights forecast.",
      due: "2026-11-18",
      amount: null,
      why: why("Disease.", ["tmax"], 0.5),
    },
    {
      id: "drought",
      category: "drought",
      priority: 3,
      risk: "moderate",
      icon: "sunny",
      title: "MOCK: Moderate drought (D1)",
      detail: "Soil moisture at the 18th percentile.",
      due: null,
      amount: null,
      why: why("Drought.", ["smap_sm", "ndvi"], 0.6),
    },
    {
      id: "pest_weevil",
      category: "pest",
      priority: 4,
      risk: "low",
      icon: "bug-outline",
      title: "MOCK: Alfalfa weevil inactive",
      detail: "Too cold for larvae.",
      due: null,
      amount: null,
      why: why("Pest.", ["tmax"], 0.6),
    },
  ],
  drought: {
    level: 2,
    label: "MOCK: Moderate drought (D1)",
    spi30: -1.1,
    spi90: -0.9,
    sm_percentile: 18,
    vhi: 38,
    why: why("Drought.", ["smap_sm", "ndvi"], 0.6),
  },
  water: {
    root_zone_depletion_mm: 118,
    taw_mm: 160,
    raw_mm: 88,
    days_to_stress: 0,
    next_irrigation_date: "2026-11-19",
    next_irrigation_mm: 22,
    season_et_mm: 1012,
    season_rain_mm: 96,
    season_irrigation_mm: 880,
    forecast_rain_7d_mm: 1.5,
    forecast_et0_7d_mm: 14,
  },
  series,
  sources,
  mock: true,
  offline: false,
});

const years = Array.from({ length: 20 }, (_, i) => 2005 + i);
const simYears = years.map((y, i) => ({
  year: y,
  yield_t_ha: 14 + 3 * Math.sin(i),
  et_mm: 1100 + 80 * Math.cos(i),
  irrigation_mm: 950 + 70 * Math.cos(i),
  rain_mm: 120 + 40 * Math.sin(i * 2),
  stress_days: Math.max(0, Math.round(8 + 6 * Math.sin(i * 1.3))),
  heat_days: Math.round(12 + 5 * Math.sin(i)),
  frost_events: i % 4 === 0 ? 1 : 0,
  harvest_date: `${y}-10-15`,
}));
const summary = {
  yield_median: 14.2,
  yield_p10: 11.4,
  yield_p90: 16.6,
  irrigation_median_mm: 950,
  et_median_mm: 1100,
  stress_days_median: 8,
  water_productivity_kg_m3: 1.3,
  failure_risk_pct: 0,
};
W("MOCK_simulate.json", {
  crop: "alfalfa",
  scenario: {
    lat: 39.4735,
    lon: -118.7774,
    crop: "alfalfa",
    planting_date: "2026-03-20",
    irrigation_strategy: "full",
    delta_t_c: 0,
    rain_factor: 1,
    years: 20,
  },
  years: simYears,
  summary,
  baseline: summary,
  why: why("Simulation.", [], 0.5),
});

const monthsCover = (crop, pattern) => pattern.map((c, m) => ({ month: m + 1, crop: c > 0 ? crop : null, cover: c }));
const strat = (id, name, is_current, score, deltas, cal) => ({
  id,
  name,
  is_current,
  total_score: score,
  slots: [{ year: 1, crop: "alfalfa", season: "perennial", start_month: 3, end_month: 10 }],
  calendar: cal,
  metrics: [
    ["water", "Water use", 980 - deltas[0] * 5, "mm/yr"],
    ["soil", "Soil health", 60 + deltas[1], "index"],
    ["income", "Income", 100 + deltas[2], "index"],
    ["pests", "Pest-cycle break", 30 + deltas[3], "index"],
    ["risk", "Climate risk", 50 + deltas[4], "index"],
    ["bare_days", "Bare-soil days", 120 - deltas[1], "days/yr"],
  ].map(([mid, label, value, unit], i) => ({
    id: mid,
    label,
    value,
    unit,
    score: Math.max(0, Math.min(100, 55 + deltas[i % 5])),
    vs_current: is_current ? 0 : deltas[i % 5],
  })),
  why_suggested: "MOCK: placeholder explanation of why this rotation was suggested.",
  evidence: ["MOCK: July ET₀ averaged 7.9 mm/day (placeholder)"],
  benefits: ["MOCK benefit"],
  info_gaps: ["MOCK gap"],
  risks_local_review: ["MOCK risk for local review"],
  sources: ["nasa_power"],
});
const calYears = (fn) => [1, 2, 3, 4].flatMap((y) => fn(y).map((c) => ({ ...c, year: y })));
W("MOCK_rotations.json", {
  strategies: [
    strat(
      "current",
      "MOCK: Continuous alfalfa",
      true,
      52,
      [0, 0, 0, 0, 0],
      calYears(() => monthsCover("alfalfa", [0.3, 0.3, 0.5, 0.8, 0.9, 0.9, 0.9, 0.9, 0.8, 0.6, 0.3, 0.3])),
    ),
    strat(
      "alt1",
      "MOCK: Alfalfa → teff → wheat + cover",
      false,
      68,
      [18, 12, -5, 25, 6],
      calYears((y) => monthsCover(y === 2 ? "teff" : "alfalfa", [0.3, 0.3, 0.2, 0, 0.6, 0.9, 0.9, 0.7, 0.4, 0.5, 0.4, 0.3])),
    ),
    strat(
      "alt2",
      "MOCK: Alfalfa → silage maize → triticale",
      false,
      61,
      [5, 6, 10, 18, -4],
      calYears((y) => monthsCover(y === 3 ? "maize_silage" : "alfalfa", [0.4, 0.4, 0.5, 0.2, 0.3, 0.8, 0.95, 0.95, 0.4, 0.5, 0.5, 0.4])),
    ),
  ],
  climate_context: ["MOCK: frost-free season lengthened (placeholder)"],
  vulnerable_periods: [{ month: 7, issue: "MOCK: peak heat and water demand", risk: "high" }],
  sources,
  disclaimer: "MOCK disclaimer: decision support only.",
});

const cy = Array.from({ length: 40 }, (_, i) => 1985 + i);
const metric = (id, label, unit, base, trend) => ({
  id,
  label,
  unit,
  values: cy.map((_, i) => Math.round((base + (trend * i) / 10 + Math.sin(i * 1.9) * base * 0.05) * 10) / 10),
  trend_per_decade: trend,
  p_value: 0.01,
  baseline_mean: base,
  recent_mean: base + trend * 3.5,
});
W("MOCK_climate.json", {
  years: cy,
  metrics: [
    metric("tmax_summer", "Summer max temperature", "°C", 31, 0.4),
    metric("frost_free_days", "Frost-free days", "days", 140, 3),
    metric("heat_days", "Days above 35 °C", "days", 12, 2.5),
    metric("precip_annual", "Annual precipitation", "mm", 130, -4),
    metric("et0_annual", "Annual reference ET₀", "mm", 1300, 12),
  ],
  monthly_normals: Array.from({ length: 12 }, (_, m) => ({
    month: m + 1,
    tmax: 8 + 24 * Math.sin((m / 11) * Math.PI),
    tmin: -6 + 18 * Math.sin((m / 11) * Math.PI),
    precip: 12 - 8 * Math.sin((m / 11) * Math.PI),
    et0: 1 + 7 * Math.sin((m / 11) * Math.PI),
  })),
  insights: ["MOCK insight: placeholder trend sentence."],
  source: sources[0],
});
console.log("fixtures written");
