import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";
import type {
  AdviceResponse,
  ClimateResponse,
  CropInfo,
  FieldInput,
  PresetLocation,
  RotationRequest,
  RotationResponse,
  SimulateRequest,
  SimulateResponse,
} from "./types";

/**
 * Data origin of every response the UI renders:
 *  - live:  fresh from the FieldShift API
 *  - cache: last good response stored on device (offline mode)
 *  - mock:  bundled MOCK fixture — ONLY used when the API was never reachable; UI shows a red banner.
 */
export type Origin = "live" | "cache" | "mock";
export interface Result<T> {
  data: T;
  origin: Origin;
  savedAt: string | null;
}

function defaultBase(): string {
  const env = process.env.EXPO_PUBLIC_API_URL;
  if (env) return env.replace(/\/$/, "");
  if (Platform.OS === "android") return "http://10.0.2.2:8000";
  if (Platform.OS === "web" && typeof window !== "undefined" && window.location?.hostname) {
    // same-origin deploys (nginx proxies /api) work out of the box; local dev falls back to :8000
    const { protocol, hostname, port } = window.location;
    if (port === "8081" || port === "19006" || port === "4173") return `${protocol}//${hostname}:8000`;
    return `${protocol}//${window.location.host}`;
  }
  return "http://localhost:8000";
}

export const API_BASE = defaultBase();
const TIMEOUT_MS = 45000;
const CACHE_PREFIX = "fieldshift:cache:v1:";

async function http<T>(path: string, body?: unknown): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(res.status, text.slice(0, 300) || res.statusText);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(`API ${status}: ${message}`);
  }
}

async function readCache<T>(key: string): Promise<{ data: T; savedAt: string } | null> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_PREFIX + key);
    return raw ? (JSON.parse(raw) as { data: T; savedAt: string }) : null;
  } catch {
    return null;
  }
}

async function writeCache<T>(key: string, data: T) {
  try {
    await AsyncStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ data, savedAt: new Date().toISOString() }));
  } catch {
    // storage full / unavailable — non-fatal
  }
}

/**
 * live → device cache → MOCK fixture. 4xx errors (bad input) are re-thrown instead of falling back,
 * so the user sees a real validation message rather than unrelated data.
 */
async function withFallback<T>(key: string, live: () => Promise<T>, mock: () => Promise<T>): Promise<Result<T>> {
  try {
    const data = await live();
    await writeCache(key, data);
    return { data, origin: "live", savedAt: new Date().toISOString() };
  } catch (err) {
    if (err instanceof ApiError && err.status >= 400 && err.status < 500) throw err;
    const cached = await readCache<T>(key);
    if (cached) return { data: cached.data, origin: "cache", savedAt: cached.savedAt };
    if (process.env.EXPO_PUBLIC_DISABLE_MOCK === "1") throw err;
    return { data: await mock(), origin: "mock", savedAt: null };
  }
}

const k = (...parts: (string | number | undefined | null)[]) => parts.map((p) => (typeof p === "number" ? p.toFixed(3) : (p ?? ""))).join("|");

export const api = {
  base: API_BASE,
  health: () => http<{ status: string; version: string }>("/api/health"),
  crops: () =>
    withFallback<CropInfo[]>(
      "crops",
      () => http("/api/crops"),
      async () => (await import("./__fixtures__/MOCK_crops.json")).default as CropInfo[],
    ),
  presets: () =>
    withFallback<PresetLocation[]>(
      "presets",
      () => http("/api/presets"),
      async () => (await import("./__fixtures__/MOCK_presets.json")).default as PresetLocation[],
    ),
  advice: (f: FieldInput) =>
    withFallback<AdviceResponse>(
      k("advice", f.lat, f.lon, f.crop, f.planting_date, f.irrigation, f.lang),
      () => http("/api/advice", f),
      async () => (await import("./__fixtures__/MOCK_advice.json")).default as unknown as AdviceResponse,
    ),
  simulate: (r: SimulateRequest) =>
    withFallback<SimulateResponse>(
      k("sim", r.lat, r.lon, r.crop, r.planting_date, r.irrigation_strategy, r.delta_t_c, r.rain_factor, r.water_allocation_mm),
      () => http("/api/simulate", r),
      async () => (await import("./__fixtures__/MOCK_simulate.json")).default as unknown as SimulateResponse,
    ),
  rotations: (r: RotationRequest) =>
    withFallback<RotationResponse>(
      k("rot", r.lat, r.lon, r.current_rotation.join(","), r.irrigation, r.lang, JSON.stringify(r.priorities)),
      () => http("/api/rotations", r),
      async () => (await import("./__fixtures__/MOCK_rotations.json")).default as unknown as RotationResponse,
    ),
  climate: (lat: number, lon: number) =>
    withFallback<ClimateResponse>(
      k("climate", lat, lon),
      () => http(`/api/climate?lat=${lat}&lon=${lon}`),
      async () => (await import("./__fixtures__/MOCK_climate.json")).default as unknown as ClimateResponse,
    ),
  exportUrl: (kind: "advice.csv" | "field.geojson", f: FieldInput) =>
    `${API_BASE}/api/export/${kind}?lat=${f.lat}&lon=${f.lon}&crop=${encodeURIComponent(f.crop)}&planting_date=${f.planting_date}&irrigation=${f.irrigation}`,
};
