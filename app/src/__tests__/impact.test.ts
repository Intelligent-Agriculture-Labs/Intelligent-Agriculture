import { impactMetrics, impactValue } from "@/components/ImpactCard";
import type { RotationPlanResponse } from "@/api/types";

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock("@react-native-async-storage/async-storage", () => require("@react-native-async-storage/async-storage/jest/async-storage-mock"));

type Impact = NonNullable<RotationPlanResponse["impact"]>;
const perHa: Impact["per_ha"] = {
  water_saved_mm_per_yr: 12,
  water_saved_m3_per_ha_per_yr: 120,
  n_fertiliser_saved_kg_ha: -90,
  co2e_avoided_kg_ha: 0,
  soil_kept_t_ha: 1.24,
  margin_gain_usd_ha: 1121,
  bare_days_fewer_per_yr: 123,
};
const base: Impact = { vs: "optimised plan", years: 4, per_ha: perHa, field_area_ha: null, field_total: null, headline: "h", method: "m" };

describe("impactMetrics", () => {
  it("drops zero metrics and keeps the story order, per hectare without an area", () => {
    const m = impactMetrics(base);
    expect(m.map((x) => x.key)).toEqual(["water", "soil", "margin", "nitrogen", "bare"]);
    expect(m[0]).toMatchObject({ value: 120, unit: "m³/ha" });
  });
  it("uses whole-field totals when the area is known", () => {
    const m = impactMetrics({
      ...base,
      field_area_ha: 5.5,
      field_total: { water_saved_m3_per_yr: 660, n_fertiliser_saved_kg: -495, co2e_avoided_kg: 0, soil_kept_t: 6.8, margin_gain_usd: 6165 },
    });
    expect(m.find((x) => x.key === "water")).toMatchObject({ value: 660, unit: "m³" });
    expect(m.find((x) => x.key === "margin")).toMatchObject({ value: 6165, unit: "$" });
  });
});

describe("impactValue", () => {
  const m = impactMetrics(base);
  const get = (k: string) =>
    impactValue(
      m.find((x) => x.key === k)!,
      "en",
    );
  it("shows savings plainly and trade-offs honestly", () => {
    expect(get("water")).toBe("120 m³/ha");
    expect(get("soil")).toBe("1.2 t/ha");
    expect(get("nitrogen")).toBe("+90 kg N/ha"); // more fertiliser needed
    expect(get("margin")).toBe("+$1,121/ha");
    expect(get("bare")).toBe("123");
  });
  it("signs a lower income with a minus", () => {
    const loss = impactMetrics({ ...base, per_ha: { ...perHa, margin_gain_usd_ha: -40 } }).find((x) => x.key === "margin")!;
    expect(impactValue(loss, "en")).toBe("−$40/ha");
  });
});
