/**
 * Pure farm / multi-field logic (no React, no storage) so it can be unit-tested:
 * ids, legacy migration, FieldRecord <-> local Field conversion, per-field merge, sync-code formatting.
 */
import type { FieldRecord, IrrigationMethod } from "@/api/types";

/** Field as used on the device. Superset of the synced FieldRecord: `as_of` (replay date) is device-local. */
export interface Field {
  id: string;
  name: string;
  lat: number;
  lon: number;
  polygon?: [number, number][];
  area_ha?: number | null;
  crop: string;
  planting_date: string;
  irrigation: IrrigationMethod;
  current_rotation: string[];
  water_allocation_mm?: number | null;
  last_irrigation_date?: string | null;
  last_irrigation_mm?: number | null;
  notes?: string | null;
  presetId?: string | null;
  replay_date?: string | null;
  /** replay date for demo farms (null = today) — device-local, never synced */
  as_of?: string | null;
  updated_at: string;
  deleted?: boolean;
}

/** What screens pass to setField/addField: id/updated_at are filled in by the store. */
export type FieldDraft = Omit<Field, "id" | "updated_at"> & { id?: string; updated_at?: string };

export function newId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c?.randomUUID) return c.randomUUID();
  const hex = "0123456789abcdef";
  let s = "";
  for (let i = 0; i < 32; i++) s += hex[Math.floor(Math.random() * 16)];
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-4${s.slice(13, 16)}-a${s.slice(17, 20)}-${s.slice(20, 32)}`;
}

export const nowIso = () => new Date().toISOString();

/** Shoelace area on an equirectangular projection — accurate to <1 % for field-sized polygons. */
export function polygonAreaHa(pts: [number, number][] | null | undefined): number {
  if (!pts || pts.length < 3) return 0;
  const lat0 = (pts.reduce((a, p) => a + p[1], 0) / pts.length) * (Math.PI / 180);
  const R = 6371000;
  const xy = pts.map(([lon, lat]) => [((R * (lon * Math.PI)) / 180) * Math.cos(lat0), (R * (lat * Math.PI)) / 180]);
  let s = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2 / 10000;
}

/** Area-weighted centroid of a polygon (falls back to the vertex mean for degenerate rings). */
export function polygonCentroid(pts: [number, number][]): { lat: number; lon: number } {
  let a = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % pts.length];
    const f = x1 * y2 - x2 * y1;
    a += f;
    cx += (x1 + x2) * f;
    cy += (y1 + y2) * f;
  }
  if (Math.abs(a) < 1e-12) {
    return { lon: pts.reduce((s, p) => s + p[0], 0) / pts.length, lat: pts.reduce((s, p) => s + p[1], 0) / pts.length };
  }
  return { lon: cx / (3 * a), lat: cy / (3 * a) };
}

/** Migrate the v1 single stored field (no id) into a Field. */
export function migrateLegacyField(old: Record<string, unknown> | null | undefined): Field | null {
  if (!old || typeof old.lat !== "number" || typeof old.lon !== "number") return null;
  const crop = typeof old.crop === "string" ? old.crop : "maize";
  return {
    id: newId(),
    name: typeof old.name === "string" && old.name ? old.name : `${(old.lat as number).toFixed(3)}, ${(old.lon as number).toFixed(3)}`,
    lat: old.lat as number,
    lon: old.lon as number,
    polygon: Array.isArray(old.polygon) && old.polygon.length >= 3 ? (old.polygon as [number, number][]) : undefined,
    crop,
    planting_date: typeof old.planting_date === "string" ? old.planting_date : new Date().toISOString().slice(0, 10),
    irrigation: (old.irrigation as IrrigationMethod) ?? "none",
    current_rotation: Array.isArray(old.current_rotation) ? (old.current_rotation as string[]) : [crop, crop, crop, crop],
    presetId: (old.presetId as string | null) ?? null,
    replay_date: (old.replay_date as string | null) ?? null,
    as_of: (old.as_of as string | null) ?? null,
    last_irrigation_date: (old.last_irrigation_date as string | null) ?? null,
    last_irrigation_mm: (old.last_irrigation_mm as number | null) ?? null,
    updated_at: nowIso(),
  };
}

export function toRecord(f: Field): FieldRecord {
  const area = f.polygon && f.polygon.length >= 3 ? Math.round(polygonAreaHa(f.polygon) * 100) / 100 : (f.area_ha ?? null);
  return {
    id: f.id,
    name: f.name,
    lat: f.lat,
    lon: f.lon,
    polygon: f.polygon && f.polygon.length >= 3 ? f.polygon : null,
    area_ha: area,
    crop: f.crop,
    planting_date: f.planting_date,
    irrigation: f.irrigation,
    current_rotation: f.current_rotation,
    water_allocation_mm: f.water_allocation_mm ?? null,
    last_irrigation_date: f.last_irrigation_date ?? null,
    last_irrigation_mm: f.last_irrigation_mm ?? null,
    notes: f.notes ?? null,
    preset_id: f.presetId ?? null,
    replay_date: f.replay_date ?? null,
    updated_at: f.updated_at,
    deleted: f.deleted ?? false,
  };
}

export function fromRecord(r: FieldRecord, local?: Field): Field {
  return {
    id: r.id,
    name: r.name,
    lat: r.lat,
    lon: r.lon,
    polygon: r.polygon && r.polygon.length >= 3 ? r.polygon : undefined,
    area_ha: r.area_ha ?? null,
    crop: r.crop,
    planting_date: r.planting_date,
    irrigation: r.irrigation,
    current_rotation: r.current_rotation?.length ? r.current_rotation : [r.crop],
    water_allocation_mm: r.water_allocation_mm ?? null,
    last_irrigation_date: r.last_irrigation_date ?? null,
    last_irrigation_mm: r.last_irrigation_mm ?? null,
    notes: r.notes ?? null,
    presetId: r.preset_id ?? null,
    replay_date: r.replay_date ?? null,
    as_of: local?.as_of ?? null, // device-local view state survives syncs
    updated_at: r.updated_at,
    deleted: r.deleted ?? false,
  };
}

const ts = (iso: string | undefined) => {
  const v = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(v) ? v : 0;
};

/**
 * Merge local fields with the server's copy, per field id: the newer updated_at wins (ties → server, which is
 * the agreed copy). Fields only on one side are kept. Tombstones (deleted=true) participate like any edit,
 * so a deletion on one device removes the field everywhere unless it was edited later elsewhere.
 */
export function mergeFields(local: Field[], remote: FieldRecord[]): Field[] {
  const byId = new Map<string, Field>();
  for (const f of local) byId.set(f.id, f);
  for (const r of remote) {
    const l = byId.get(r.id);
    if (!l || ts(r.updated_at) >= ts(l.updated_at)) byId.set(r.id, fromRecord(r, l));
  }
  // stable order: by first appearance in local, then new remote fields
  const order = [...local.map((f) => f.id), ...remote.map((r) => r.id)];
  const seen = new Set<string>();
  const out: Field[] = [];
  for (const id of order) {
    if (seen.has(id)) continue;
    seen.add(id);
    const f = byId.get(id);
    if (f) out.push(f);
  }
  return out;
}

/** True if any local field changed after the given instant (used to decide whether a push is still needed). */
export function hasChangesSince(fields: Field[], sinceIso: string | null): boolean {
  if (!sinceIso) return fields.length > 0;
  const t0 = ts(sinceIso);
  return fields.some((f) => ts(f.updated_at) > t0);
}

/** Sync codes are shown as XXXX-XXXX; users may type them in any case, with or without separators. */
export function normalizeSyncCode(input: string): string {
  return input.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function formatSyncCode(input: string): string {
  const n = normalizeSyncCode(input);
  return n.length > 4 ? `${n.slice(0, 4)}-${n.slice(4)}` : n;
}

export function isValidSyncCode(input: string): boolean {
  return /^[A-Z0-9]{8}$/.test(normalizeSyncCode(input));
}
