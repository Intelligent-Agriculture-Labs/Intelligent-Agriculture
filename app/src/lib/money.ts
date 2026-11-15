/**
 * Money in the field's local currency (ADR-027). The backend computes in USD with the field's country prices and
 * sends `*_local` values plus the ISO 4217 code; this formats them. Falls back to "1,234 KES" when Intl lacks the
 * currency (e.g. Hermes builds without full ICU).
 */
import type { Economics } from "@/api/types";

export function formatMoney(value: number, currency: string | undefined, lang = "en", maxFrac = 0): string {
  const code = currency || "USD";
  try {
    return new Intl.NumberFormat(lang, { style: "currency", currency: code, maximumFractionDigits: maxFrac, minimumFractionDigits: 0 }).format(value);
  } catch {
    return `${value.toLocaleString(lang, { maximumFractionDigits: maxFrac })} ${code}`;
  }
}

/** Parameters of the provenance line: country, currency and the World Bank exchange rate used. */
export function economicsParams(e: Economics | undefined | null): { country: string; currency: string; rate: string; year: string } | null {
  if (!e) return null;
  return {
    country: e.country?.name ?? "",
    currency: e.currency.code,
    rate: e.currency.per_usd >= 100 ? e.currency.per_usd.toFixed(0) : e.currency.per_usd.toFixed(2),
    year: e.currency.year ? String(e.currency.year) : "",
  };
}
