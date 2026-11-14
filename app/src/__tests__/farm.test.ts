import {
  type Field,
  formatSyncCode,
  fromRecord,
  hasChangesSince,
  isValidSyncCode,
  mergeFields,
  migrateLegacyField,
  normalizeSyncCode,
  polygonAreaHa,
  polygonCentroid,
  toRecord,
} from "@/state/farm";
import { qrPath } from "@/components/QrCode";

const base: Field = {
  id: "a",
  name: "North field",
  lat: 39.44,
  lon: -118.84,
  crop: "alfalfa",
  planting_date: "2022-03-15",
  irrigation: "flood",
  current_rotation: ["alfalfa"],
  updated_at: "2026-11-14T10:00:00.000Z",
};

describe("farm merge", () => {
  it("newer edit wins per field, both directions", () => {
    const local = [
      { ...base, name: "local newer", updated_at: "2026-11-14T12:00:00.000Z" },
      { ...base, id: "b", name: "b local" },
    ];
    const remote = [
      toRecord({ ...base, name: "remote older", updated_at: "2026-11-14T11:00:00.000Z" }),
      toRecord({ ...base, id: "b", name: "b remote newer", updated_at: "2026-11-14T13:00:00.000Z" }),
    ];
    const m = mergeFields(local, remote);
    expect(m.find((f) => f.id === "a")?.name).toBe("local newer");
    expect(m.find((f) => f.id === "b")?.name).toBe("b remote newer");
  });

  it("keeps fields that exist on only one side and preserves order", () => {
    const m = mergeFields([base], [toRecord({ ...base, id: "c", name: "from phone" })]);
    expect(m.map((f) => f.id)).toEqual(["a", "c"]);
  });

  it("propagates deletions (tombstones) and keeps device-local replay state", () => {
    const local = [{ ...base, as_of: "2025-07-15" }];
    const remote = [toRecord({ ...base, deleted: true, updated_at: "2026-11-14T15:00:00.000Z" })];
    const m = mergeFields(local, remote);
    expect(m[0].deleted).toBe(true);
    expect(m[0].as_of).toBe("2025-07-15");
  });

  it("record round trip keeps synced content and computes area", () => {
    const poly: [number, number][] = [
      [-118.85, 39.44],
      [-118.84, 39.44],
      [-118.84, 39.45],
      [-118.85, 39.45],
    ];
    const r = toRecord({ ...base, polygon: poly, presetId: "fallon_nv" });
    expect(r.preset_id).toBe("fallon_nv");
    expect(r.area_ha).toBeGreaterThan(90);
    expect(r).not.toHaveProperty("as_of");
    const back = fromRecord(r);
    expect(back.polygon).toEqual(poly);
    expect(back.presetId).toBe("fallon_nv");
  });

  it("detects local changes since the last sync", () => {
    expect(hasChangesSince([base], null)).toBe(true);
    expect(hasChangesSince([base], "2026-11-14T11:00:00.000Z")).toBe(false);
    expect(hasChangesSince([base], "2026-11-14T09:00:00.000Z")).toBe(true);
  });
});

describe("legacy migration", () => {
  it("turns the v1 single field into a field with id and timestamp", () => {
    const f = migrateLegacyField({ lat: 1, lon: 2, crop: "maize", planting_date: "2026-03-01", irrigation: "none", name: "Home", current_rotation: ["maize"] });
    expect(f).not.toBeNull();
    expect(f!.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(f!.name).toBe("Home");
    expect(Date.parse(f!.updated_at)).toBeGreaterThan(0);
  });
  it("ignores garbage", () => {
    expect(migrateLegacyField(null)).toBeNull();
    expect(migrateLegacyField({ lat: "x" })).toBeNull();
  });
});

describe("geometry", () => {
  it("area of a 100 m x 100 m square is ~1 ha", () => {
    const d = 100 / 111320;
    const sq: [number, number][] = [
      [0, 0],
      [d, 0],
      [d, d],
      [0, d],
    ];
    expect(polygonAreaHa(sq)).toBeCloseTo(1, 1);
    const c = polygonCentroid(sq);
    expect(c.lat).toBeCloseTo(d / 2, 8);
    expect(c.lon).toBeCloseTo(d / 2, 8);
  });
});

describe("sync codes", () => {
  it("normalises and formats user input", () => {
    expect(normalizeSyncCode(" k7qf-2m9x ")).toBe("K7QF2M9X");
    expect(formatSyncCode("k7qf2m9x")).toBe("K7QF-2M9X");
    expect(isValidSyncCode("K7QF-2M9X")).toBe(true);
    expect(isValidSyncCode("K7QF-2M9")).toBe(false);
  });
  it("encodes a join link as a QR matrix", () => {
    const { size, d } = qrPath("fieldshift://join?code=K7QF-2M9X");
    expect(size).toBeGreaterThanOrEqual(29); // version >= 2 + quiet zone
    expect(d.length).toBeGreaterThan(100);
  });
});
