"""Build the static showcase site (site/dist) from the template, real screenshots, the demo video and validation numbers.

    python3 scripts/build_site.py [--repo https://github.com/<you>/fieldshift]

Publish site/dist with GitHub Pages (or any static host). No login is needed to view it (Space Apps rule).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "dist"
MEDIA = ROOT / "media"
SHOTS = [  # (file, caption) — first existing variant wins
    (["web-welcome-mobile.png", "web-onboarding-mobile.png"], "Start in under a minute"),
    (["web-home.png", "web-home-mobile.png"], "This week: three clear actions"),
    (["web-detect-mobile.png", "web-fields-desktop.png"], "Tap your field — AI finds the boundary"),
    (["web-satellite-mobile.png", "ios-satellite.png"], "Sentinel-2 + AI management zones"),
    (["web-plan-years-mobile.png", "web-plan-mobile.png"], "Multi-year rotation plan with impact"),
    (["ios-home-replay.png"], "iPhone"),
    (["android-home-replay.png"], "Android"),
]


def main() -> None:
    repo = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else "https://github.com/YOUR-ACCOUNT/fieldshift"
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    shutil.copy(ROOT / "assets" / "icon.svg", OUT / "assets" / "icon.svg")
    figs = []
    for variants, cap in SHOTS:
        f = next((MEDIA / v for v in variants if (MEDIA / v).exists()), None)
        if f:
            shutil.copy(f, OUT / "assets" / f.name)
            figs.append(f'<figure><img src="assets/{f.name}" alt="{cap}" loading="lazy"><figcaption>{cap}</figcaption></figure>')
    vid = MEDIA / "fieldshift-demo-30s.mp4"
    if vid.exists():
        shutil.copy(vid, OUT / "assets" / vid.name)
    poster = next((MEDIA / v for v in ("web-home-desktop.png", "web-home.png") if (MEDIA / v).exists()), None)
    if poster:
        shutil.copy(poster, OUT / "assets" / "poster.png")
    impact_items = []
    imp = SITE / "impact.json"
    if imp.exists():
        for it in json.loads(imp.read_text()):
            impact_items.append(f'<div class="stat"><b>{it["value"]}</b><span>{it["label"]}</span></div>')
    val = []
    res = ROOT / "docs" / "validation" / "results.json"
    ml = ROOT / "docs" / "validation" / "drought_ml.json"
    if res.exists():
        r = json.loads(res.read_text())
        try:
            val.append(f'<div class="stat"><b>r = {r["et0"]["cordoba_es"]["monthly_mm"]["r"]:.3f}</b><span>crop water demand vs. ERA5 (monthly)</span></div>')
            val.append(f'<div class="stat"><b>#{r["yield"]["rank_of_2012"]} of {r["yield"]["n_years"]}</b><span>2012 Iowa drought: worst simulated season</span></div>')
            val.append(f'<div class="stat"><b>ρ = {r["usdm"]["ames_ia"]["spearman_level_v2"]:.2f}</b><span>drought status vs. U.S. Drought Monitor</span></div>')
        except (KeyError, TypeError):
            pass
    if ml.exists():
        m = json.loads(ml.read_text())
        val.append(f'<div class="stat"><b>{100 * m["ml_heldout"]["within1_acc"]:.0f} %</b><span>AI drought classifier within ±1 category on unseen counties</span></div>')
    html = (SITE / "template.html").read_text()
    html = html.replace("{{SHOTS}}", "\n".join(figs)).replace("{{IMPACT}}", "\n".join(impact_items)).replace("{{VALIDATION}}", "\n".join(val))
    html = html.replace("{{REPO_URL}}", repo)
    (OUT / "index.html").write_text(html)
    build_deck(repo, impact_items, val)
    print("built", OUT / "index.html", f"{len(figs)} screenshots")


DECK_SHOTS = {
    "welcome": ["web-welcome-mobile.png", "web-onboarding-mobile.png"],
    "home": ["web-home-mobile.png", "web-home.png", "web-replay-home-mobile.png"],
    "plan": ["web-plan-years-mobile.png", "web-plan-mobile.png"],
}


def build_deck(repo: str, impact_items: list[str], val: list[str]) -> None:
    """site/deck.html -> site/dist/deck.html and media/fieldshift-deck.pdf (7 slides, 16:9) via headless Chrome."""
    import subprocess

    html = (SITE / "deck.html").read_text()
    for key, variants in DECK_SHOTS.items():
        f = next((MEDIA / v for v in variants if (MEDIA / v).exists()), None)
        if f:
            shutil.copy(f, OUT / "assets" / f.name)
            html = html.replace("{{" + key + "}}", f"assets/{f.name}")
    tiles = [t.replace('class="stat"', 'class="tile"') for t in impact_items[:2]]
    html = html.replace("{{IMPACT}}", "\n".join(tiles)).replace("{{VALIDATION}}", "\n".join(t.replace('class="stat"', 'class="tile"') for t in val))
    html = html.replace("{{REPO}}", repo.replace("https://", ""))
    (OUT / "deck.html").write_text(html)
    chrome = next((c for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("chromium") or "", shutil.which("google-chrome") or "") if c and Path(c).exists()), None)
    if not chrome:
        print("no Chrome found; deck.html built, PDF skipped")
        return
    pdf = MEDIA / "fieldshift-deck.pdf"
    import tempfile

    with tempfile.TemporaryDirectory() as prof:  # own profile: works while the user's Chrome is open
        r = subprocess.run(
            [chrome, "--headless", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf}", (OUT / "deck.html").as_uri()],
            capture_output=True, text=True,
        )
    if r.returncode != 0:
        print("PDF export failed:", r.stderr[-500:])
        return
    print("deck", pdf)


if __name__ == "__main__":
    main()
