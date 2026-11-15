// PNG exports of the IA logo for the Expo app (app.json references these files).
//   node scripts/brand/export_icons.mjs            (run make_logo.py first; uses sharp from app/node_modules)
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const sharp = createRequire(path.join(root, "app", "package.json"))("sharp");
const A = (p) => path.join(root, p);
const png = (svg, size) => sharp(A(svg), { density: Math.max(72, (72 * size) / 1024 * 2) }).resize(size, size);
const jobs = [
  ["app/assets/icon.svg", "app/assets/icon.png", 1024, { flatten: true }],
  ["app/assets/splash.svg", "app/assets/splash-icon.png", 1024],
  ["app/assets/adaptive-fg.svg", "app/assets/android-icon-foreground.png", 1024],
  ["app/assets/adaptive-bg.svg", "app/assets/android-icon-background.png", 1024, { flatten: true }],
  ["app/assets/adaptive-mono.svg", "app/assets/android-icon-monochrome.png", 1024],
  ["app/assets/favicon.svg", "app/assets/favicon.png", 48],
];
for (const [src, out, size, o = {}] of jobs) {
  let img = png(src, size);
  if (o.flatten) img = img.flatten({ background: "#07110b" });
  await img.png({ compressionLevel: 9 }).toFile(A(out));
  console.log("wrote", out);
}
