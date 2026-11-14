// Renders brand SVGs in assets/ to the PNGs referenced by app.json. Run: node scripts/make-icons.mjs
import sharp from "sharp";
const out = [
  ["assets/icon.svg", "assets/icon.png", 1024],
  ["assets/icon.svg", "assets/favicon.png", 48],
  ["assets/splash.svg", "assets/splash-icon.png", 1024],
  ["assets/adaptive-fg.svg", "assets/android-icon-foreground.png", 1024],
  ["assets/adaptive-fg.svg", "assets/android-icon-monochrome.png", 1024],
];
for (const [src, dst, size] of out) {
  await sharp(src, { density: 300 }).resize(size, size).png().toFile(dst);
  console.log("wrote", dst);
}
await sharp({ create: { width: 1024, height: 1024, channels: 4, background: "#2f6b3a" } })
  .png()
  .toFile("assets/android-icon-background.png");
console.log("wrote assets/android-icon-background.png");
