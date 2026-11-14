import en from "@/i18n/locales/en.json";
import es from "@/i18n/locales/es.json";
import fr from "@/i18n/locales/fr.json";
import sw from "@/i18n/locales/sw.json";
import hi from "@/i18n/locales/hi.json";
import de from "@/i18n/locales/de.json";

type Tree = { [k: string]: string | Tree };
const flatten = (o: Tree, p = ""): Record<string, string> =>
  Object.entries(o).reduce<Record<string, string>>((acc, [k, v]) => {
    const key = p ? `${p}.${k}` : k;
    if (typeof v === "string") acc[key] = v;
    else Object.assign(acc, flatten(v, key));
    return acc;
  }, {});
const placeholders = (s: string) => (s.match(/{{\s*\w+\s*}}/g) ?? []).map((x) => x.replace(/\s/g, "")).sort();

const base = flatten(en as Tree);
const locales = { es, fr, sw, hi, de } as Record<string, Tree>;

describe.each(Object.entries(locales))("locale %s", (_code, data) => {
  const flat = flatten(data);
  it("has exactly the English keys", () => {
    expect(Object.keys(flat).sort()).toEqual(Object.keys(base).sort());
  });
  it("has no empty strings", () => {
    for (const [k, v] of Object.entries(flat)) expect([k, v.trim().length > 0]).toEqual([k, true]);
  });
  it("keeps the same interpolation placeholders", () => {
    for (const [k, v] of Object.entries(base)) expect([k, placeholders(flat[k] ?? "")]).toEqual([k, placeholders(v)]);
  });
});
