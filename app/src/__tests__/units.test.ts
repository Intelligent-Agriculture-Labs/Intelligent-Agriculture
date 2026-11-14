import { acToHa, cToF, convert, fmt, fToC, haToAc, inToMm, mmToIn, tHaToTonAc } from "@/lib/units";

describe("unit conversion", () => {
  it("converts length", () => {
    expect(mmToIn(25.4)).toBeCloseTo(1, 10);
    expect(inToMm(2)).toBeCloseTo(50.8, 10);
  });
  it("converts temperature (absolute)", () => {
    expect(cToF(0)).toBe(32);
    expect(cToF(100)).toBe(212);
    expect(fToC(cToF(37.5))).toBeCloseTo(37.5, 10);
  });
  it("converts area and yield", () => {
    expect(haToAc(1)).toBeCloseTo(2.4710538, 6);
    expect(acToHa(haToAc(3.3))).toBeCloseTo(3.3, 10);
    expect(tHaToTonAc(10)).toBeCloseTo(4.46089, 5);
  });
  it("leaves metric values untouched", () => {
    expect(convert(12, "mm", "metric")).toEqual({ value: 12, unit: "mm" });
  });
  it("maps wire units to imperial display units", () => {
    expect(convert(25.4, "mm", "imperial")).toEqual({ value: 1, unit: "in" });
    expect(convert(20, "°C", "imperial").unit).toBe("°F");
    expect(convert(1, "°C/decade", "imperial").value).toBeCloseTo(1.8, 10);
    expect(convert(0.3, "m³/m³", "imperial")).toEqual({ value: 0.3, unit: "m³/m³" });
  });
  it("formats with units and handles missing values", () => {
    expect(fmt(22, "mm", "metric")).toBe("22 mm");
    expect(fmt(25.4, "mm", "imperial")).toBe("1 in");
    expect(fmt(20, "°C", "metric")).toBe("20°C");
    expect(fmt(null, "mm", "metric")).toBe("—");
  });
});
