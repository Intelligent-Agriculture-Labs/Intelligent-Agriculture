"""IA (Intelligent Agriculture) brand: generates the logo SVGs from geometry.

    python3 -m venv /tmp/brandenv && /tmp/brandenv/bin/pip install fonttools
    /tmp/brandenv/bin/python scripts/brand/make_logo.py      # writes assets/*.svg and app/assets/*.svg
    node scripts/brand/export_icons.mjs                       # PNG icons for the app (needs app/node_modules)

The mark: a satellite (apex) on its orbit looks down at a field; its two swath lines are the
legs of an "A", the glowing horizon of the planet is the crossbar, and the crop rows of the field
converge on the satellite. Colours and glow follow the film (video/film.html): night #050807,
mint #86dc98, atmosphere blue. Text is converted to outlines (Manrope 800, Inter 600, SIL OFL),
so the SVGs render the same everywhere without fonts.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = Path.home() / ".cache" / "ia-brand-fonts"
FONT_URLS = {
    "manrope": "https://github.com/google/fonts/raw/main/ofl/manrope/Manrope%5Bwght%5D.ttf",
    "inter": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf",
}

# ---------------------------------------------------------------- geometry (1024 x 1024)
AP = (512, 262)  # satellite / apex of the A
PC, PR = (512, 1930), 1360  # planet; horizon (crossbar) at y = 570
R2 = PR - 250  # lower edge of the field parcel
HALF = math.radians(23)  # half-angle of the swath (A legs)


def _ray_circle(d, r):
    fx, fy = AP[0] - PC[0], AP[1] - PC[1]
    b = 2 * (fx * d[0] + fy * d[1])
    c = fx * fx + fy * fy - r * r
    t = (-b - math.sqrt(b * b - 4 * c)) / 2
    return AP[0] + t * d[0], AP[1] + t * d[1]


DL = (-math.sin(HALF), math.cos(HALF))
DR = (math.sin(HALF), math.cos(HALF))
FL, FR = _ray_circle(DL, R2), _ray_circle(DR, R2)
HL, HR = _ray_circle(DL, PR), _ray_circle(DR, PR)
HY = PC[1] - PR


def _ring(r):
    return f"M{PC[0] - r} {PC[1]} a{r} {r} 0 1 0 {2 * r} 0 a{r} {r} 0 1 0 {-2 * r} 0 Z"


def _rows(n):
    out = []
    m = n * 2 + 1
    for i in range(0, m, 2):
        a0, a1 = -HALF + 2 * HALF * i / m, -HALF + 2 * HALF * (i + 1) / m
        out.append(
            f"M{AP[0]} {AP[1]} L{AP[0] + 900 * math.sin(a0):.1f} {AP[1] + 900 * math.cos(a0):.1f} "
            f"L{AP[0] + 900 * math.sin(a1):.1f} {AP[1] + 900 * math.cos(a1):.1f} Z"
        )
    return out


def mark(
    *,
    tile: bool = True,
    rx: int = 228,
    orbit: bool = True,
    glow: float = 1.0,
    sw: int = 58,
    rows_n: int = 9,
    arcs: bool = True,
    layer: str = "all",  # all | bg | fg | mono
    scale: float = 1.0,
    p: str = "",  # id prefix, so several marks can live in one document
    anim: bool = False,  # ids on the parts + legs/rows as separate paths (for the film)
) -> str:
    """The IA mark as a standalone SVG document."""
    legs = f"M{FL[0]:.1f} {FL[1]:.1f} L{AP[0]} {AP[1]} L{FR[0]:.1f} {FR[1]:.1f}"
    tri = f"M{AP[0]} {AP[1]} L{AP[0] + 1400 * DL[0]:.1f} {AP[1] + 1400 * DL[1]:.1f} L{AP[0] + 1400 * DR[0]:.1f} {AP[1] + 1400 * DR[1]:.1f} Z"
    band = _ring(PR) + " " + _ring(R2)
    d = [
        f'<linearGradient id="{p}bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f251a"/><stop offset=".55" stop-color="#08130d"/><stop offset="1" stop-color="#040806"/></linearGradient>',
        f'<radialGradient id="{p}halo" cx="512" cy="{HY}" r="600" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#86dc98" stop-opacity=".26"/><stop offset=".5" stop-color="#3f8fd0" stop-opacity=".10"/><stop offset="1" stop-color="#3f8fd0" stop-opacity="0"/></radialGradient>',
        f'<linearGradient id="{p}leg" x1="0" y1="{AP[1]}" x2="0" y2="{FL[1]:.0f}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#ffffff"/><stop offset=".4" stop-color="#a6f3b6"/><stop offset="1" stop-color="#43c48a"/></linearGradient>',
        f'<linearGradient id="{p}land" x1="0" y1="{HY}" x2="0" y2="1024" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#174f33"/><stop offset="1" stop-color="#061a0f"/></linearGradient>',
        f'<linearGradient id="{p}soil" x1="0" y1="{HY}" x2="0" y2="{FL[1]:.0f}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#3a9d66"/><stop offset="1" stop-color="#14583a"/></linearGradient>',
        f'<linearGradient id="{p}row" x1="0" y1="{HY}" x2="0" y2="{FL[1]:.0f}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#e4ffe8"/><stop offset="1" stop-color="#6fd99a"/></linearGradient>',
        f'<linearGradient id="{p}rim" x1="0" y1="0" x2="1024" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#4f9cff" stop-opacity="0"/><stop offset=".28" stop-color="#7ab8ff" stop-opacity=".85"/><stop offset=".5" stop-color="#dcffe6"/><stop offset=".72" stop-color="#7ab8ff" stop-opacity=".85"/><stop offset="1" stop-color="#4f9cff" stop-opacity="0"/></linearGradient>',
        f'<linearGradient id="{p}beam" x1="0" y1="{AP[1]}" x2="0" y2="{HY}" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#86dc98" stop-opacity="0"/><stop offset="1" stop-color="#86dc98" stop-opacity=".2"/></linearGradient>',
        f'<clipPath id="{p}planet"><circle cx="{PC[0]}" cy="{PC[1]}" r="{PR}"/></clipPath>',
        f'<clipPath id="{p}sky"><path d="M-2000 -2000 H3000 V3000 H-2000 Z {_ring(PR)}" clip-rule="evenodd"/></clipPath>',
        f'<clipPath id="{p}inA"><path d="{tri}"/></clipPath>',
        f'<clipPath id="{p}band"><path d="{band}" clip-rule="evenodd"/></clipPath>',
        f'<filter id="{p}blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="22"/></filter>',
    ]
    if tile:
        d.append(f'<clipPath id="{p}tile"><rect width="1024" height="1024" rx="{rx}"/></clipPath>')

    bg, fg = [], []
    if layer in ("all", "bg"):
        bg.append(
            f'<rect width="1024" height="1024" fill="url(#{p}bg)"/><rect width="1024" height="1024" fill="url(#{p}halo)"/>'
        )
    sc = []  # scaled content
    if layer in ("all", "bg"):
        sc.append(f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{PR}" fill="url(#{p}land)"/>')
        if arcs:
            sc.append(
                f'<g clip-path="url(#{p}planet)">'
                + "".join(
                    f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{r}" fill="none" stroke="#9ef0b0" stroke-width="{w}" opacity="{o}"/>'
                    for r, w, o in ((R2 - 70, 5, 0.22), (R2 - 150, 4, 0.14), (R2 - 240, 3, 0.08))
                )
                + "</g>"
            )
    if layer in ("all", "fg"):

        def i(name):  # element ids for the film's logo animation (video/film.html)
            return f' id="{p}e-{name}"' if anim else ""

        rows = (
            "".join(f'<path{i(f"row{k}")} fill="url(#{p}row)" d="{r}"/>' for k, r in enumerate(_rows(rows_n)))
            if anim
            else f'<path fill="url(#{p}row)" d="{" ".join(_rows(rows_n))}"/>'
        )
        sc.append(
            f'<path{i("beam")} d="M{AP[0]} {AP[1]} L{FL[0]:.1f} {FL[1]:.1f} L{FR[0]:.1f} {FR[1]:.1f} Z" fill="url(#{p}beam)" clip-path="url(#{p}sky)"/>'
        )
        sc.append(
            f'<g{i("field")} clip-path="url(#{p}inA)"><path{i("soil")} d="{band}" fill-rule="evenodd" fill="url(#{p}soil)"/>'
            f'<g clip-path="url(#{p}band)">{rows}</g></g>'
        )
        sc.append(
            f'<g{i("rim")}><circle cx="{PC[0]}" cy="{PC[1]}" r="{PR}" fill="none" stroke="url(#{p}rim)" stroke-width="44" filter="url(#{p}blur)" opacity=".9"/>'
        )
        sc.append(
            f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{PR}" fill="none" stroke="url(#{p}rim)" stroke-width="11"/></g>'
        )
        if orbit:
            sc.append(
                f'<ellipse{i("orbit")} cx="{AP[0]}" cy="{AP[1]}" rx="292" ry="60" fill="none" stroke="#d6efdc" stroke-opacity=".34" stroke-width="8" transform="rotate(-12 {AP[0]} {AP[1]})"/>'
            )
        leg_paths = (
            [
                (f"M{AP[0]} {AP[1]} L{FL[0]:.1f} {FL[1]:.1f}", "L"),
                (f"M{AP[0]} {AP[1]} L{FR[0]:.1f} {FR[1]:.1f}", "R"),
            ]
            if anim
            else [(legs, "")]
        )
        if glow:
            for dd, k in leg_paths:
                sc.append(
                    f'<path{i("legglow" + k)} d="{dd}" fill="none" stroke="#86dc98" stroke-width="{sw + 10}" stroke-linejoin="round" stroke-linecap="round" filter="url(#{p}blur)" opacity="{0.38 * glow:.2f}"/>'
                )
        for dd, k in leg_paths:
            sc.append(
                f'<path{i("leg" + k)} d="{dd}" fill="none" stroke="url(#{p}leg)" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        if glow:
            sc.append(
                f'<circle{i("satglow")} cx="{AP[0]}" cy="{AP[1]}" r="72" fill="#e9ffe9" filter="url(#{p}blur)" opacity="{0.75 * glow:.2f}"/>'
            )
        sc.append(f'<circle{i("sat")} cx="{AP[0]}" cy="{AP[1]}" r="46" fill="#ffffff"/>')
    if layer == "mono":  # one colour, for the Android themed icon
        sc.append(
            f'<g fill="#fff"><g clip-path="url(#{p}inA)"><g clip-path="url(#{p}band)"><path d="{" ".join(_rows(rows_n))}"/></g></g>'
            f'<path d="{legs}" fill="none" stroke="#fff" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{AP[0]}" cy="{AP[1]}" r="50"/>'
            f'<path d="M{HL[0]:.1f} {HL[1]:.1f} A{PR} {PR} 0 0 1 {HR[0]:.1f} {HR[1]:.1f}" fill="none" stroke="#fff" stroke-width="22"/></g>'
        )
    if scale != 1.0:
        o = 512 * (1 - scale)
        content = f'<g transform="translate({o:.1f} {o:.1f}) scale({scale})">{"".join(sc)}</g>'
    else:
        content = "".join(sc)
    open_g = f'<g clip-path="url(#{p}tile)">' if tile else "<g>"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">'
        f"<defs>{''.join(d)}</defs>{open_g}{''.join(bg)}{content}{''.join(fg)}</g></svg>"
    )


SMALL = dict(orbit=False, sw=84, rows_n=5, glow=0.6, arcs=False)  # tuned for 16-48 px

# ---------------------------------------------------------------- text to outlines


def _font(name, wght):
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    f = FONT_DIR / f"{name}.ttf"
    if not f.exists():
        subprocess.run(["curl", "-fsSL", "-o", str(f), FONT_URLS[name]], check=True)
    t = TTFont(f)
    axes = {"wght": wght}
    if "opsz" in [a.axisTag for a in t["fvar"].axes]:
        axes["opsz"] = 32
    return instantiateVariableFont(t, axes)


_FONTS: dict = {}


def text_path(txt, name, wght, size, x, y, tracking=0.0):
    """Outline path of `txt` with its baseline at y, and the first glyph's ink starting at x."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen

    f = _FONTS.setdefault((name, wght), _font(name, wght))
    gs, cmap, upm, hmtx = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm, f["hmtx"]
    sc = size / upm
    b = BoundsPen(gs)
    gs[cmap[ord(txt[0])]].draw(b)
    cx = x - b.bounds[0] * sc
    out = []
    for ch in txt:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs, lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[g].draw(TransformPen(pen, (sc, 0, 0, -sc, cx, y)))
        out.append(pen.getCommands())
        cx += hmtx[g][0] * sc + tracking * size
    return " ".join(c for c in out if c), cx - tracking * size


def _inner(svg):
    return svg.split(">", 1)[1].rsplit("</svg>", 1)[0]


def lockup(theme="dark"):
    """Horizontal logo: mark · IA | INTELLIGENT / AGRICULTURE."""
    H = 320
    ink = "#eef4ef" if theme == "dark" else "#0c1d13"
    sub = "#86dc98" if theme == "dark" else "#2b7a4b"
    rule = "#eef4ef" if theme == "dark" else "#0c1d13"
    cap_ia = 172
    base = H / 2 + cap_ia / 2
    top = base - cap_ia
    d_ia, end_ia = text_path("IA", "manrope", 800, cap_ia * 2000 / 1440, H + 70, base, tracking=-0.01)
    xr = end_ia + 54
    cap_s, tr = 56, 0.13
    s_s = cap_s * 2048 / 1490
    d1, e1 = text_path("INTELLIGENT", "inter", 600, s_s, xr + 57, top + cap_s, tracking=tr)
    d2, e2 = text_path("AGRICULTURE", "inter", 600, s_s, xr + 57, base, tracking=tr)
    w = max(e1, e2) + 4
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {H}" width="{w:.0f}" height="{H}" role="img" aria-label="IA, Intelligent Agriculture">'
        f"<title>IA · Intelligent Agriculture</title>"
        f'<g transform="scale({H / 1024})">{_inner(mark(p="m"))}</g>'
        f'<path fill="{ink}" d="{d_ia}"/>'
        f'<rect x="{xr:.1f}" y="{top:.1f}" width="3" height="{cap_ia}" rx="1.5" fill="{rule}" fill-opacity="{0.22 if theme == "dark" else 0.18}"/>'
        f'<path fill="{sub}" d="{d1} {d2}"/></svg>'
    )


def main():
    out = {
        "assets/logo.svg": lockup("dark"),
        "assets/logo-light.svg": lockup("light"),
        "assets/logo-mark.svg": mark(),
        "assets/logo-mark-small.svg": mark(**SMALL),
        "assets/icon.svg": mark(tile=False),
        "app/assets/icon.svg": mark(tile=False),
        "app/assets/splash.svg": mark(),
        "app/assets/adaptive-fg.svg": mark(tile=False, layer="fg", scale=0.62),
        "app/assets/adaptive-bg.svg": mark(tile=False, layer="bg", scale=0.62),
        "app/assets/adaptive-mono.svg": mark(tile=False, layer="mono", scale=0.62, glow=0),
        "app/assets/favicon.svg": mark(**SMALL),
        "video/logo-mark-anim.svg": mark(tile=False, layer="fg", anim=True, p="tm-"),
        "video/logo-mark-tile-anim.svg": mark(anim=True, p="em-"),
    }
    for path, svg in out.items():
        svg = re.sub(r"\s+", " ", svg)
        (ROOT / path).write_text(svg + "\n")
        print("wrote", path)


if __name__ == "__main__":
    sys.exit(main())
