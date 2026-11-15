/**
 * No user-visible English hard-coded in .tsx screens/components: JSX text and literal label-like props must go
 * through t(). Mirrors the "app hard-coded text" check of scripts/check_i18n.py. Exempt a line with `i18n: ok`.
 */
import fs from "fs";
import path from "path";

const SRC = path.resolve(__dirname, "..");
const JSX_TEXT = />([^<>{}`]*[A-Za-z]{3,}[^<>{}`]*)</g;
const JSX_PROP =
  /\b(label|title|subtitle|placeholder|accessibilityLabel|accessibilityHint|hint|message|text|caption)=("[^"]*[A-Za-z]{2,}[^"]*"|\{\s*"[^"]*[A-Za-z]{2,}[^"]*"\s*\})/g;
const OK_VALUES = new Set(['"OK"', '"YYYY-MM-DD"', '"XXXX-XXXX"']);

function tsxFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === "__tests__" || e.name === "node_modules" ? [] : tsxFiles(p);
    return p.endsWith(".tsx") ? [p] : [];
  });
}

const words = (s: string) => (s.match(/[A-Za-z]{2,}/g) ?? []).length;

it("has no hard-coded user-visible English in .tsx files", () => {
  const found: string[] = [];
  for (const f of tsxFiles(SRC)) {
    fs.readFileSync(f, "utf8")
      .split("\n")
      .forEach((line, i) => {
        const s = line.trim();
        if (line.includes("i18n: ok") || /^(\/\/|\*|\/\*|import )/.test(s)) return;
        for (const m of line.matchAll(JSX_TEXT)) {
          const txt = m[1].trim();
          if (txt && !/[=&|;()]|=>/.test(txt) && txt.includes(" ") && words(txt) >= 2) found.push(`${path.relative(SRC, f)}:${i + 1} ${txt}`);
        }
        for (const m of line.matchAll(JSX_PROP)) {
          const v = m[2].replace(/^\{\s*|\s*\}$/g, "");
          if (!OK_VALUES.has(v)) found.push(`${path.relative(SRC, f)}:${i + 1} ${m[1]}=${v}`);
        }
      });
  }
  expect(found).toEqual([]);
});
