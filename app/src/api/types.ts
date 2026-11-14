/**
 * FieldShift API contract (v1) — single source of truth shared by backend (FastAPI/pydantic)
 * and client (Expo). The backend's pydantic models in backend/fieldshift/schemas.py mirror this.
 * All units are SI/metric on the wire; the client converts for display.
 */

export type Risk = "low" | "moderate" | "high" | "severe";
export type Lang = "en" | "es" | "fr" | "sw" | "hi" | "de";
export type IrrigationMethod = "none" | "drip" | "sprinkler" | "pivot" | "furrow" | "flood";

export interface FieldInput {
  lat: number;
  lon: number;
  crop: string; // crop id from /api/crops, e.g. "alfalfa"
  planting_date: string; // ISO date, for perennials = stand establishment / season green-up
  irrigation: IrrigationMethod;
  /** optional: polygon drawn by user (GeoJSON [lon,lat] ring), area computed server-side */
  polygon?: [number, number][];
  /** optional: water available for the season in mm (deficit scheduling) */
  water_allocation_mm?: number | null;
  lang?: Lang;
  /** farmer-reported last irrigation (gross amount at the field, mm) — sharpens the water balance */
  last_irrigation_date?: string | null;
  last_irrigation_mm?: number | null;
  /** "today" override for demo / back-testing, ISO date */
  as_of?: string | null;
}

export interface SourceRef {
  id: string; // "nasa_power", "smap_l3e", "modis_ndvi", "mod16", "ecostress_esi", "openmeteo_forecast", "era5", "srtm", "soilgrids", "usdm"
  name: string;
  provider: string; // "NASA LaRC", "NASA/ORNL DAAC", ...
  url: string;
  resolution: string; // "0.5° × 0.625° (~50 km)", "9 km", "250 m"
  latency: string; // "~2 days"
  last_date: string | null; // last observation date actually used
  is_nasa: boolean;
  status: "live" | "cache" | "demo" | "unavailable";
}

export interface SeriesPoint {
  date: string;
  value: number | null;
}
export interface Series {
  id: string; // "et0", "precip", "soil_depletion", "smap_sm", "ndvi", "ndvi_normal", "tmax", ...
  label: string;
  unit: string;
  points: SeriesPoint[];
  normal?: SeriesPoint[]; // climatological normal for the same days, if available
  source: string; // SourceRef.id
  kind?: "observed" | "modelled" | "forecast";
}

export interface WhyBlock {
  summary: string; // plain-language one paragraph
  steps: string[]; // the reasoning chain, each a short sentence with numbers
  series: string[]; // Series ids to plot in the Why view
  model: string; // "FAO-56 dual... water balance"
  model_doc: string; // anchor in docs/MODELS.md
  confidence: number; // 0..1
  confidence_note: string; // why the confidence is what it is
  caveats: string[]; // e.g. "SMAP pixel is 9 km; your field is 2 ha"
  sources: string[]; // SourceRef ids
}

export interface ActionCard {
  id: string; // "irrigate", "drought", "disease_late_blight", "pest_alfalfa_weevil", "sowing", "frost", "heat"
  category: "water" | "drought" | "disease" | "pest" | "planning" | "weather";
  priority: number; // 1 = most urgent
  risk: Risk;
  icon: string; // ionicons name
  title: string; // "Irrigate 22 mm before Thursday"
  detail: string; // one sentence
  due: string | null; // ISO date
  amount?: { value: number; unit: string } | null; // e.g. 22 mm
  why: WhyBlock;
}

export interface DroughtStatus {
  level: 0 | 1 | 2 | 3 | 4 | 5; // 0 = none, 1..5 = D0..D4 style
  label: string; // "Moderate drought (D1)"
  spi30: number | null;
  spi90: number | null;
  spei90?: number | null;
  sm_percentile: number | null; // 0..100
  vhi: number | null; // 0..100
  /** AI drought classifier (contiguous U.S. only, where it was validated); level replaces the rule-based level */
  ml?: {
    level: number;
    probabilities: number[]; // None, D0..D4
    rules_level: number;
    model: string;
    heldout_within1_acc: number;
    heldout_spearman: number;
    n_counties: number;
  } | null;
  why: WhyBlock;
}

export interface AdviceResponse {
  field: FieldInput & {
    elevation_m: number | null;
    slope_pct: number | null;
    soil: SoilInfo | null;
    area_ha: number | null;
  };
  generated_at: string;
  as_of: string;
  cards: ActionCard[]; // ALL cards ranked; UI shows top 3 on the home screen
  drought: DroughtStatus;
  water: WaterState;
  series: Series[];
  sources: SourceRef[];
  mock: boolean; // true only if any value was synthetic (must be shown in UI)
  offline: boolean; // served from pre-cached demo data
}

export interface SoilInfo {
  texture: string; // "loam"
  clay_pct: number | null;
  sand_pct: number | null;
  soc_g_kg: number | null;
  taw_mm_per_m: number; // total available water per m root depth
  source: string;
}

export interface WaterState {
  root_zone_depletion_mm: number;
  taw_mm: number;
  raw_mm: number;
  days_to_stress: number | null;
  next_irrigation_date: string | null;
  next_irrigation_mm: number | null;
  season_et_mm: number;
  season_rain_mm: number;
  season_irrigation_mm: number;
  forecast_rain_7d_mm: number;
  forecast_et0_7d_mm: number;
}

/* ---------- What-if simulator ---------- */
export interface SimulateRequest {
  lat: number;
  lon: number;
  crop: string;
  planting_date: string; // month-day used across years, ISO date with any year
  irrigation_strategy: "rainfed" | "full" | "deficit_75" | "deficit_50" | "allocation";
  water_allocation_mm?: number | null;
  delta_t_c?: number; // climate scenario: + °C
  rain_factor?: number; // e.g. 0.8 = 20% less rain
  years?: number; // how many past seasons to simulate (default 20)
}
export interface SimYear {
  year: number;
  yield_t_ha: number;
  et_mm: number;
  irrigation_mm: number;
  rain_mm: number;
  stress_days: number;
  heat_days: number;
  frost_events: number;
  harvest_date: string;
}
export interface SimulateResponse {
  crop: string;
  scenario: SimulateRequest;
  years: SimYear[];
  summary: {
    yield_median: number;
    yield_p10: number; // bad year
    yield_p90: number;
    irrigation_median_mm: number;
    et_median_mm: number;
    stress_days_median: number;
    water_productivity_kg_m3: number;
    failure_risk_pct: number; // % of years with yield < 50% of median-of-baseline
  };
  baseline?: SimulateResponse["summary"]; // same crop/date, no scenario changes
  daily_example?: Series[]; // daily canopy cover, soil depletion for the median year
  why: WhyBlock;
}

/* ---------- Rotation explorer (core of the Field Shift challenge) ---------- */
export interface Priorities {
  water: number; // 0..1 weights
  soil: number;
  income: number;
  pests: number;
  risk: number; // climate-risk aversion
}
export interface RotationRequest {
  lat: number;
  lon: number;
  current_rotation: string[]; // crop ids in order, one per season slot; e.g. ["alfalfa","alfalfa","alfalfa","alfalfa"]
  irrigation: IrrigationMethod;
  water_allocation_mm?: number | null;
  priorities: Priorities;
  lang?: Lang;
}
export interface RotationSlot {
  year: number; // 1..N
  crop: string;
  season: "spring" | "summer" | "fall" | "winter" | "perennial" | "cover";
  start_month: number; // 1..12
  end_month: number;
}
export interface RotationMetric {
  id: "water" | "soil" | "income" | "pests" | "risk" | "erosion" | "nitrogen" | "bare_days";
  label: string;
  value: number; // in unit
  unit: string;
  score: number; // 0..100, higher = better for farmer
  vs_current: number; // delta of score vs current rotation
}
export interface RotationStrategy {
  id: string;
  name: string; // "Alfalfa → teff → winter wheat + cover"
  is_current: boolean;
  slots: RotationSlot[];
  calendar: {
    month: number;
    year: number;
    crop: string | null;
    cover: number;
  }[]; // 0..1 ground cover per month
  metrics: RotationMetric[];
  total_score: number; // weighted by priorities, 0..100
  why_suggested: string;
  evidence: string[]; // numbers from NASA data, e.g. "July ET0 averaged 7.9 mm/day (POWER 1985-2024)"
  benefits: string[];
  info_gaps: string[];
  risks_local_review: string[];
  sources: string[];
}
export interface RotationResponse {
  strategies: RotationStrategy[]; // current first, then ranked alternatives (>= 3 total)
  climate_context: string[]; // key local signals: "Frost-free season lengthened 11 days since 1985"
  vulnerable_periods: { month: number; issue: string; risk: Risk }[];
  sources: SourceRef[];
  disclaimer: string;
}

/* ---------- Climate trends ---------- */
export interface ClimateResponse {
  years: number[];
  metrics: {
    id: string; // "tmax_summer", "gdd", "frost_free_days", "heat_days", "precip_annual", "precip_growing", "et0_annual", "heavy_rain_days", "last_spring_frost_doy", "first_fall_frost_doy"
    label: string;
    unit: string;
    values: (number | null)[];
    trend_per_decade: number;
    p_value: number;
    baseline_mean: number; // first 15 years
    recent_mean: number; // last 10 years
  }[];
  monthly_normals: {
    month: number;
    tmax: number;
    tmin: number;
    precip: number;
    et0: number;
  }[];
  insights: string[];
  source: SourceRef;
}

export interface CropInfo {
  id: string;
  name: string;
  family: string;
  type: "annual" | "perennial" | "cover";
  n_fixing: boolean;
  root_depth_m: number;
  season_days: number;
  typical_yield_t_ha: number;
  icon: string;
}

export interface PresetLocation {
  id: string;
  name: string;
  lat: number;
  lon: number;
  crop: string;
  planting_date: string;
  irrigation: IrrigationMethod;
  current_rotation: string[];
  story: string;
  cached: boolean;
  /** a past date with an active season, to replay real advice for demos (sent as FieldInput.as_of) */
  replay_date?: string | null;
  /** real field outline [lon, lat] ring (detected/traced on sub-metre imagery) */
  polygon?: [number, number][] | null;
}

/* ---------- Terrain maps (POST /api/terrain) ---------- */
export interface TerrainRequest {
  lat: number;
  lon: number;
  crop: string;
  polygon?: [number, number][] | null; // [lon, lat] ring
}
export interface TerrainLegendItem {
  color: string;
  label: string;
  share_pct?: number; // share of the field area in this class
}
export interface TerrainLayer {
  id: "elevation" | "slope" | "erosion" | "wetness" | "frost" | "zones" | "hillshade";
  label: string;
  unit: string;
  png: string; // relative URL, e.g. /api/terrain/png/<key>/slope.png — web-mercator aligned with `bounds`
  legend: TerrainLegendItem[];
  stats: { mean?: number; p10?: number; p90?: number; max?: number }; // over the field (polygon or 150 m radius)
  why: string;
}
export interface TerrainZone {
  id: "erosion" | "wet" | "frost" | "core";
  color: string;
  label: string;
  share_pct: number;
  advice: string;
}
export interface TerrainResponse {
  key: string;
  bounds: { south: number; west: number; north: number; east: number };
  cell_m: number;
  field: { area_ha: number; polygon: boolean; texture: string; annual_precip_mm: number };
  layers: TerrainLayer[];
  zones: TerrainZone[];
  zone_advice: TerrainZone[]; // zones covering >= 5 % of the field (planning advice)
  sources: SourceRef[];
  caveats: string[];
}

/* ---------- Season planner (POST /api/planner) ---------- */
export interface PlannerRequest {
  lat: number;
  lon: number;
  crop: string;
  planting_date: string;
  irrigation: IrrigationMethod;
  water_allocation_mm?: number | null;
  as_of?: string | null;
}
export interface PlannerResponse {
  crop: string;
  season_start: string;
  years: [number, number];
  sowing_scan: {
    date: string;
    yield_median: number;
    yield_p10: number;
    irrigation_median_mm: number;
    frost_risk_pct: number;
    heat_days_median: number;
    score: number;
  }[]; // empty for perennials
  window: { start: string; end: string; best: string } | null;
  stages: { label: string; date: string; spread_days: number }[]; // perennials: cutting dates
  operations: { date: string; label: string; kind: "sow" | "stage" | "harvest" | "scout" | "water" }[];
  water_budget: { month: number; et0: number; etc: number; eta: number; rain: number; irr: number }[]; // mm, median season
  water: {
    season_irrigation_median_mm: number;
    full_need_median_mm: number;
    allocation_mm: number | null;
    coverage_pct: number | null;
    efficiency: number;
    note: string | null;
  };
  risk_calendar: { month: number; frost_pct: number; heat_pct: number }[];
  why: string;
  sources: string[];
}

/* ---------- Farm & multi-field sync (phone <-> PC), no account ----------
 * A farm is identified by a random farm_id (secret, stored on each device) and a short human sync_code
 * (e.g. "K7QF-2M9X") that another device can enter to join. Server merges fields per id by updated_at
 * (last writer wins; deletions are tombstones with deleted=true). */
export interface FieldRecord {
  id: string; // uuid generated on the device
  name: string;
  lat: number;
  lon: number;
  polygon?: [number, number][] | null; // [lon, lat] ring drawn on satellite imagery
  area_ha?: number | null;
  crop: string;
  planting_date: string;
  irrigation: IrrigationMethod;
  current_rotation: string[];
  water_allocation_mm?: number | null;
  last_irrigation_date?: string | null;
  last_irrigation_mm?: number | null;
  notes?: string | null;
  preset_id?: string | null;
  replay_date?: string | null;
  history?: RotationYear[]; // what was grown on this field (past years)
  plan?: RotationYear[]; // the farmer's multi-year rotation plan
  updated_at: string; // ISO datetime, set by the device on every change
  deleted?: boolean;
}
export interface FarmSettings {
  lang?: Lang;
  units?: "metric" | "imperial";
  expert?: boolean;
  active_field_id?: string | null;
}
export interface Farm {
  farm_id: string;
  sync_code: string;
  name: string;
  fields: FieldRecord[]; // includes tombstones (deleted=true) so other devices learn about deletions
  settings: FarmSettings;
  version: number; // increments on every server write
  updated_at: string;
}
// POST /api/farms {name?, fields?, settings?} -> Farm            (create)
// GET  /api/farms/{farm_id} -> Farm                               (pull)
// PUT  /api/farms/{farm_id} {name?, fields, settings?} -> Farm    (push; server merges per field by updated_at)
// POST /api/farms/join {sync_code} -> Farm                        (pair another device)

/* ---------- Field satellite analysis (POST /api/satellite) — Sentinel-2 L2A 10 m ----------
 * Asynchronous: the first call starts a job and returns {status:"processing", progress}; poll the same
 * request every ~3 s until status === "done" (results are cached per field). */
export interface SatelliteRequest {
  lat: number;
  lon: number;
  polygon?: [number, number][] | null;
  crop?: string;
  start?: string | null; // default: 365 days before end
  end?: string | null; // default: today (or as_of)
}
export interface SatelliteScene {
  id: string;
  date: string;
  cloud_pct: number; // scene cloud cover (metadata)
  valid_pct: number; // share of field pixels clear (SCL mask)
  ndvi_mean: number | null;
  ndvi_p10: number | null;
  ndvi_p90: number | null;
}
export interface SatelliteResponse {
  status: "processing" | "done" | "error";
  progress?: number; // 0..1
  message?: string;
  field_key?: string;
  bounds?: { south: number; west: number; north: number; east: number };
  scenes?: SatelliteScene[];
  timeseries?: SeriesPoint[]; // field-mean NDVI per clear scene
  smoothed?: SeriesPoint[]; // gap-filled, Savitzky–Golay smoothed daily NDVI
  latest?: { date: string; truecolor_png: string; ndvi_png: string } | null; // relative URLs, aligned with bounds
  phenology?: {
    greenup: string | null;
    peak: string | null;
    peak_ndvi: number | null;
    senescence: string | null;
    bare_periods: { start: string; end: string }[];
    season_type: string; // e.g. "single season", "double crop", "perennial / irrigated", "bare / fallow"
    harvest_events?: string[]; // cuttings/harvests detected from space (NDVI drops)
  };
  zones?: {
    png: string;
    k: number;
    method: string; // "k-means on multi-date NDVI + terrain (standardized)"
    silhouette: number | null;
    legend: { color: string; label: string; share_pct: number; ndvi_mean: number }[];
    advice: string[];
  } | null;
  kcb_now?: number | null; // satellite-derived basal crop coefficient (NDVI -> Kcb)
  sources?: SourceRef[];
  caveats?: string[];
}

/* ---------- Accounts (email + password) ----------
 * Accounts own one farm (fields, plans, settings) so a farmer logs in on phone and PC.
 * The sync-code flow still works for sharing a farm with a family member without an account.
 * Auth: `Authorization: Bearer <token>`; tokens are opaque, valid 90 days. */
export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}
export interface AuthResponse {
  token: string;
  user: User;
  farm: Farm; // the account's farm (created on register; local fields can be uploaded with register)
}
// POST /api/auth/register {email, password (>= 8 chars), name?, fields?: FieldRecord[], settings?: FarmSettings} -> AuthResponse
// POST /api/auth/login {email, password} -> AuthResponse
// POST /api/auth/logout (Bearer) -> {ok: true}
// GET  /api/auth/me (Bearer) -> {user: User, farm: Farm}
// GET  /api/me/farm (Bearer) -> Farm ;  PUT /api/me/farm (Bearer) {name?, fields, settings?} -> Farm (per-field merge)
// POST /api/auth/password (Bearer) {old_password, new_password} -> {ok: true}
// DELETE /api/auth/me (Bearer) {password} -> {ok: true}   (deletes account + farm)

/* ---------- Per-field multi-year rotation plan ----------
 * FieldRecord gets `history` (what was grown) and `plan` (what the farmer intends). The checker evaluates
 * each planned year biologically (disease/pest host breaks, return intervals, nitrogen, allelopathy, soil cover)
 * and agronomically (simulated yield & water at this field from NASA weather) and proposes improvements. */
export interface RotationYear {
  year: number; // calendar year of the main crop's harvest
  crop: string; // main crop id
  cover_crop?: string | null; // optional cover / catch crop after the main crop
}
export interface RotationIssue {
  id: string; // e.g. "return_interval", "shared_pathogen:sclerotinia", "n_deficit", "bare_soil", "allelopathy", "water_shortfall"
  severity: "info" | "caution" | "problem";
  title: string; // plain language: "Potato again too soon"
  explanation: string; // plain language, 1–3 sentences, with numbers
  suggestion: string | null; // what to do instead
  sources: string[]; // citations from the knowledge base
}
export interface RotationYearCheck {
  year: number;
  crop: string;
  cover_crop: string | null;
  verdict: "good" | "caution" | "problem";
  score: number; // 0..100
  issues: RotationIssue[];
  benefits: string[]; // plain language: "Peas left ~40 kg N/ha for this wheat"
  sim: {
    yield_t_ha: number; // expected (median) with rotation effects applied
    yield_p10: number; // bad year
    irrigation_mm: number;
    water_use_mm: number;
    n_balance_kg_ha: number; // + surplus / − deficit to supply with fertiliser
    margin_usd_ha: number; // indicative
    bare_days: number;
    erosion_t_ha: number | null; // RUSLE for this field (needs polygon/terrain)
    rotation_effect_pct: number; // yield effect of predecessors (+/−)
  };
}
export interface RotationPlanRequest {
  lat: number;
  lon: number;
  polygon?: [number, number][] | null;
  irrigation: IrrigationMethod;
  water_allocation_mm?: number | null;
  history: RotationYear[]; // past years (most recent last), may be empty
  plan: RotationYear[]; // planned years (consecutive), 1..8
  priorities?: Priorities;
  lang?: Lang;
  optimize?: boolean; // also search for a better plan
}
export interface RotationPlanResponse {
  years: RotationYearCheck[];
  summary: {
    score: number;
    verdict: "good" | "caution" | "problem";
    headline: string; // plain language: "Good plan — one change would cut disease risk"
    total_margin_usd_ha: number;
    avg_irrigation_mm: number;
    n_balance_kg_ha: number; // over the plan
    disease_pressure: { pathogen: string; name: string; level: "low" | "medium" | "high"; years: number[] }[];
  };
  suggestions: { title: string; explanation: string; plan: RotationYear[]; score: number; score_gain: number }[];
  optimized: { plan: RotationYear[]; score: number; explanation: string } | null;
  /** current plan vs. improved (optimised or best suggestion) plan */
  impact: {
    vs: string;
    years: number;
    per_ha: {
      water_saved_mm_per_yr: number;
      water_saved_m3_per_ha_per_yr: number;
      n_fertiliser_saved_kg_ha: number;
      co2e_avoided_kg_ha: number;
      soil_kept_t_ha: number;
      margin_gain_usd_ha: number;
      bare_days_fewer_per_yr: number;
    };
    field_area_ha: number | null;
    field_total: { water_saved_m3_per_yr: number; n_fertiliser_saved_kg: number; co2e_avoided_kg: number; soil_kept_t: number; margin_gain_usd: number } | null;
    headline: string; // plain language incl. trade-offs
    method: string;
  } | null;
  crops_available: string[]; // crops that fit this field's climate
  sources: SourceRef[];
  disclaimer: string;
}
// POST /api/rotations/plan -> RotationPlanResponse

/* ---------- Plain-language glossary (GET /api/glossary?lang=en) ---------- */
export interface GlossaryEntry {
  id?: string; // stable key, e.g. "et0"
  term: string; // "ET₀"
  plain: string; // "How much water a well-watered lawn would lose to the air today — the weather's thirst."
  why_it_matters: string;
}

/* ---------- Low-bandwidth text advice: POST /api/advice/text?name=&max_chars=320 (body: FieldInput) ---------- */
export interface AdviceText {
  text: string; // <= max_chars, header + top actions + rain, in FieldInput.lang
  chars: number;
  sms_parts: number;
}
