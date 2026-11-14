// Render video/film.html frame by frame (deterministic render(t)) and mux with the score.
//   node video/render.mjs [--from 0 --to 30 --fps 30 --out video/build/film.mp4] [--stills 1,3.5,7]
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.join(root, "app", "package.json"));
const { chromium } = require("playwright");
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const FPS = +arg("fps", 30), FROM = +arg("from", 0), TO = +arg("to", 30);
const OUT = path.resolve(root, arg("out", "video/build/film.mp4"));
const STILLS = arg("stills", "");
fs.mkdirSync(path.dirname(OUT), { recursive: true });

// tiny static server (canvas getImageData needs same-origin, not file://)
const types = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml" };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split("?")[0]));
  if (!p.startsWith(root) || !fs.existsSync(p)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": types[path.extname(p)] || "application/octet-stream" });
  fs.createReadStream(p).pipe(res);
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
page.on("pageerror", e => console.error("pageerror", e.message));
await page.goto(`http://localhost:${port}/video/film.html`);
await page.evaluate(() => window.ready);

if (STILLS) {
  for (const s of STILLS.split(",").map(Number)) {
    await page.evaluate(t => window.render(t), s);
    await page.screenshot({ path: path.join(path.dirname(OUT), `still_${s}.jpg`), type: "jpeg", quality: 85 });
    console.log("still", s);
  }
} else {
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT.replace(/\.mp4$/, "_video.mp4")], { stdio: ["pipe", "inherit", "inherit"] });
  const n = Math.round((TO - FROM) * FPS);
  const t0 = Date.now();
  for (let f = 0; f < n; f++) {
    await page.evaluate(t => window.render(t), FROM + f / FPS);
    let buf;
    for (let attempt = 1; ; attempt++) {  // a busy machine can stall one screenshot: retry instead of losing the render
      try { buf = await page.screenshot({ type: "png", timeout: 120000 }); break; }
      catch (e) { if (attempt >= 4) throw e; console.log(`frame ${f}: retry ${attempt} (${e.name})`); await page.evaluate(t => window.render(t), FROM + f / FPS); }
    }
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (f % 60 === 0) console.log(`frame ${f}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on("close", r));
  console.log("video done");
}
await browser.close();
server.close();
