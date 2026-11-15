/* eslint-disable import/no-named-as-default-member -- i18n.t on the shared instance, as in i18n/index.ts */
import i18n from "i18next";

export type UnitSystem = "metric" | "imperial";

/** Units that contain words: shown in the app language (locales: units.*). Numeric units are language-neutral. */
const UNIT_KEYS: Record<string, string> = {
  days: "units.days",
  doy: "units.doy",
  "days/yr": "units.daysYr",
  "mm/yr": "units.mmYr",
  "t/ha/yr": "units.tHaYr",
  "USD/ha/yr": "units.usdHaYr",
  index: "units.index",
  "% (lower better)": "units.pctLowerBetter",
  "kg N/ha/yr": "units.kgNHaYr",
  "°C/decade": "units.cDecade",
  "°F/decade": "units.fDecade",
  "mm/decade": "units.mmDecade",
  "in/decade": "units.inDecade",
};

/** Display form of a (converted) unit in the current language. */
export function unitLabel(unit: string): string {
  const key = UNIT_KEYS[unit];
  return key && i18n.isInitialized ? i18n.t(key, { defaultValue: unit }) : unit;
}

const MM_PER_IN = 25.4;
const M2_PER_ACRE = 4046.8564224;

export const mmToIn = (mm: number) => mm / MM_PER_IN;
export const inToMm = (inch: number) => inch * MM_PER_IN;
export const cToF = (c: number) => (c * 9) / 5 + 32;
export const fToC = (f: number) => ((f - 32) * 5) / 9;
/** temperature *difference* (e.g. +2 °C scenario) */
export const dCToDF = (dc: number) => (dc * 9) / 5;
export const haToAc = (ha: number) => (ha * 10000) / M2_PER_ACRE;
export const acToHa = (ac: number) => (ac * M2_PER_ACRE) / 10000;
/** t/ha -> short tons per acre */
export const tHaToTonAc = (tha: number) => tha * 0.446089;

function round(v: number, digits: number) {
  const f = 10 ** digits;
  return Math.round(v * f) / f;
}

/** Convert a value whose wire unit is `unit` to the user's system. Returns value + display unit. */
export function convert(value: number, unit: string, system: UnitSystem): { value: number; unit: string } {
  if (system === "metric") return { value, unit };
  switch (unit) {
    case "mm":
      return { value: mmToIn(value), unit: "in" };
    case "mm/day":
      return { value: mmToIn(value), unit: "in/day" };
    case "°C":
    case "C":
      return { value: cToF(value), unit: "°F" };
    case "°C/decade":
      return { value: dCToDF(value), unit: "°F/decade" };
    case "ha":
      return { value: haToAc(value), unit: "ac" };
    case "t/ha":
      return { value: tHaToTonAc(value), unit: "ton/ac" };
    case "mm/decade":
      return { value: mmToIn(value), unit: "in/decade" };
    default:
      return { value, unit };
  }
}

/** Format a value with sensible precision after unit conversion. */
export function fmt(value: number | null | undefined, unit: string, system: UnitSystem, digits?: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const c = convert(value, unit, system);
  const d = digits ?? (c.unit === "in" || c.unit === "in/day" ? 1 : Math.abs(c.value) < 10 ? 1 : 0);
  const sep = c.unit.startsWith("°") || c.unit === "%" ? "" : " ";
  const u = unitLabel(c.unit);
  return `${round(c.value, d).toLocaleString(undefined, { maximumFractionDigits: d })}${u ? sep + u : ""}`;
}
