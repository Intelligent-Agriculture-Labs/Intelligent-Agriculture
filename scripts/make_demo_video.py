"""Assemble the ≤ 30 s demo video from REAL app screen captures with burned-in English captions.

    python3 scripts/make_demo_video.py            # -> media/fieldshift-demo-30s.mp4

No SI-generated imagery: every frame is a screenshot or screen recording of the running app, or a
plain title card. Requires ffmpeg. Shots are defined below (image path, caption, seconds); missing
images are skipped with a warning so the script works with whatever captures exist.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"
OUT = MEDIA / "fieldshift-demo-30s.mp4"
FONT = next(
    (
        f
        for f in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if Path(f).exists()
    ),
    None,
)
W, H = 1920, 1080
BG = "0x1d3b24"  # brand dark green

# (images shown side by side, caption, seconds). Follows the official Space Apps 30 s template:
# 0:00 team · 0:02 challenge / inspiration · 0:05 title + tagline · 0:10 how it works + NASA data · 0:20 future vision
SHOTS: list[tuple[list[str], str, float]] = [
    ([], "Team IA|NASA Space Apps Challenge 2026", 2.0),
    (["web-climate-mobile.png"], "Challenge: Field Shift. In Fallon, Nevada, days above 35 °C doubled since 1984", 3.0),
    (["web-welcome-mobile.png", "web-home.png"], "IA: 40 years of NASA data, turned into this week's farm decisions", 5.0),
    (["web-detect-mobile.png", "web-satellite-mobile.png", "web-map-mobile.png"], "Tap your field: AI finds it. Sentinel-2 zones, SRTM erosion and frost maps", 3.5),
    (["web-home.png", "web-replay-why-mobile.png"], "3 actions a week, each one tap from its NASA POWER, SMAP and MODIS evidence", 3.5),
    (["web-plan-years-mobile.png", "web-plan-years-check-mobile.png"], "Rotation plan per field: disease, nitrogen, soil, water, and its impact", 3.0),
    (["web-share-text-mobile.png", "ios-home-replay.png", "android-home-replay.png"], "Web, iOS, Android, offline, SMS, 6 languages: for any farm on Earth", 5.0),
    ([], "Next: co-design with farmers|Extension services · GPM IMERG rain · GRACE-FO groundwater · on-farm trials", 5.0),
]


def esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def render_shot(images: list[Path], caption: str, secs: float, out: Path) -> None:
    inputs: list[str] = []
    filters: list[str] = [f"color=c={BG}:s={W}x{H}:d={secs}[bg]"]
    last = "bg"
    n = len(images)
    box_h = H - 220
    for i, img in enumerate(images):
        inputs += ["-loop", "1", "-t", str(secs), "-i", str(img)]
        slot_w = W // max(1, n)
        filters.append(f"[{i}:v]crop=iw:'min(ih,iw*2.2)':0:0,scale=w={slot_w - 80}:h={box_h}:force_original_aspect_ratio=decrease[s{i}]")
        x = f"{i * slot_w}+({slot_w}-w)/2"
        filters.append(f"[{last}][s{i}]overlay=x={x}:y=60[o{i}]")
        last = f"o{i}"
    if FONT:
        if not images:  # title card: big title + subtitle
            title, _, sub = caption.partition("|")
            filters.append(
                f"[{last}]drawtext=fontfile='{FONT}':text='{esc(title)}':fontcolor=white:fontsize=84:x=(w-tw)/2:y=h/2-120,"
                f"drawtext=fontfile='{FONT}':text='{esc(sub)}':fontcolor=0xd9f2c2:fontsize=48:x=(w-tw)/2:y=h/2+10,"
                f"drawtext=fontfile='{FONT}':text='Real app screen captures · Data\\: NASA POWER, SMAP, MODIS, SRTM':fontcolor=0xa3c4a8:fontsize=28:x=(w-tw)/2:y=h-90[v]"
            )
        else:
            filters.append(
                f"[{last}]drawbox=x=0:y=ih-150:w=iw:h=150:color=black@0.55:t=fill,"
                f"drawtext=fontfile='{FONT}':text='{esc(caption)}':fontcolor=white:fontsize=46:x=(w-tw)/2:y=h-102[v]"
            )
    else:
        filters.append(f"[{last}]null[v]")
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-t",
        str(secs),
        "-r",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    with tempfile.TemporaryDirectory() as td:
        parts = []
        total = 0.0
        for k, (imgs, cap, secs) in enumerate(SHOTS):
            paths = [MEDIA / i for i in imgs]
            missing = [p.name for p in paths if not p.exists()]
            paths = [p for p in paths if p.exists()]
            if imgs and not paths:
                print(f"skip shot {k}: missing {missing}")
                continue
            if missing:
                print(f"shot {k}: missing {missing}, using {[p.name for p in paths]}")
            part = Path(td) / f"p{k:02d}.mp4"
            render_shot(paths, cap, secs, part)
            parts.append(part)
            total += secs
        lst = Path(td) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c",
                "copy",
                str(OUT),
            ],
            check=True,
        )
    print(f"wrote {OUT} ({total:.0f} s, {OUT.stat().st_size / 1e6:.1f} MB)")
    if total > 30:
        sys.exit("video longer than the 30 s limit")


if __name__ == "__main__":
    main()
