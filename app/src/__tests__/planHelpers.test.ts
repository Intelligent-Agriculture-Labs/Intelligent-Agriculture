import { addPlanYear, defaultPlanYears, normalizeHistory, normalizePlan, removeLastPlanYear, setPlanCrop } from "@/state/farm";
import { groupCrops } from "@/components/kit";
import type { CropInfo, RotationYear } from "@/api/types";

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock("@react-native-async-storage/async-storage", () => require("@react-native-async-storage/async-storage/jest/async-storage-mock"));

const y = (year: number, crop: string, cover_crop: string | null = null): RotationYear => ({ year, crop, cover_crop });

describe("defaultPlanYears", () => {
  it("starts this year before September and next year after", () => {
    expect(defaultPlanYears(new Date(Date.UTC(2026, 2, 1)))).toEqual([2026, 2027, 2028, 2029]);
    expect(defaultPlanYears(new Date(Date.UTC(2026, 9, 1)), 3)).toEqual([2027, 2028, 2029]);
  });
});

describe("normalizePlan", () => {
  it("keeps known years and fills gaps with the fallback crop", () => {
    const plan = normalizePlan([y(2027, "soybean", "rye"), y(2031, "wheat")], [2026, 2027, 2028], "maize");
    expect(plan).toEqual([y(2026, "maize"), y(2027, "soybean", "rye"), y(2028, "maize")]);
  });
  it("handles a missing plan", () => {
    expect(normalizePlan(undefined, [2026], "wheat")).toEqual([y(2026, "wheat")]);
  });
});

describe("setPlanCrop", () => {
  const plan = [y(2026, "maize"), y(2027, "maize")];
  it("changes only the chosen year and returns a new array", () => {
    const next = setPlanCrop(plan, 2027, "soybean");
    expect(next).toEqual([y(2026, "maize"), y(2027, "soybean")]);
    expect(plan[1].crop).toBe("maize");
  });
  it("sets and clears a cover crop", () => {
    const withCover = setPlanCrop(plan, 2026, "rye", "cover_crop");
    expect(withCover[0].cover_crop).toBe("rye");
    expect(setPlanCrop(withCover, 2026, "", "cover_crop")[0].cover_crop).toBeNull();
  });
});

describe("addPlanYear / removeLastPlanYear", () => {
  it("appends the next calendar year up to 8 years", () => {
    let plan = [y(2026, "maize")];
    plan = addPlanYear(plan, "wheat");
    expect(plan[1]).toEqual(y(2027, "wheat"));
    for (let i = 0; i < 10; i++) plan = addPlanYear(plan, "wheat");
    expect(plan).toHaveLength(8);
    expect(plan[7].year).toBe(2033);
  });
  it("never removes the last remaining year", () => {
    expect(removeLastPlanYear([y(2026, "maize"), y(2027, "wheat")])).toEqual([y(2026, "maize")]);
    expect(removeLastPlanYear([y(2026, "maize")])).toEqual([y(2026, "maize")]);
  });
});

describe("normalizeHistory", () => {
  it("returns the n years before the plan, keeping known crops", () => {
    expect(normalizeHistory([y(2024, "potato"), y(2019, "oat")], 2026, 3, "maize")).toEqual([y(2023, "maize"), y(2024, "potato"), y(2025, "maize")]);
  });
});

describe("groupCrops", () => {
  const crop = (id: string, name: string, family: string) => ({ id, name, family }) as unknown as CropInfo;
  const crops = [crop("wheat", "Wheat", "Poaceae"), crop("pea", "Field pea", "Fabaceae"), crop("maize", "Maize", "Poaceae"), crop("bean", "Bean", "Fabaceae")];
  it("groups by plant family with crops sorted by name", () => {
    const groups = groupCrops(crops, "");
    expect(groups.map((g) => g.family).sort()).toEqual(["Fabaceae", "Poaceae"]);
    const poa = groups.find((g) => g.family === "Poaceae")!;
    expect(poa.crops.map((c) => c.id)).toEqual(["maize", "wheat"]);
  });
  it("filters by name, id or family", () => {
    expect(groupCrops(crops, "pea").flatMap((g) => g.crops.map((c) => c.id))).toEqual(["pea"]);
    expect(
      groupCrops(crops, "fabac")
        .flatMap((g) => g.crops.map((c) => c.id))
        .sort(),
    ).toEqual(["bean", "pea"]);
    expect(groupCrops(crops, "zzz")).toEqual([]);
  });
});
