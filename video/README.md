# FieldShift film (30 s)

A motion-designed film built entirely in code. Every frame is rendered from `film.html` by a deterministic `render(t)` function (Playwright, 30 fps, 1920 × 1080).

`./video/build.sh` rebuilds it into `media/fieldshift-demo-30s.mp4`. You need ffmpeg, Node with the app's Playwright, and the backend venv.

| File | What it does |
|---|---|
| `fetch_assets.py` | Downloads the NASA GIBS Blue Marble texture (for the 3D globe) and Esri World Imagery mosaics at zoom 3–18 around the Fallon field (for the dive from orbit). Not committed. |
| `fallon_heat.json`, `fallon_polygon.json` | Real data: the app's NASA POWER heat-day series and baseline/recent means, and the demo field outline. |
| `score.py` | The original score: 96 BPM, D minor, synthesised with numpy/scipy. No samples and no generative-AI audio. |
| `film.html` | All scenes: the globe (per-pixel orthographic projection), the zoom pyramid, the field outline drawing itself, kinetic type, 3D phones with real app screenshots from `media/`, counters, a language carousel and the end globe with the demo fields. |
| `render.mjs` | Renders frames to ffmpeg. `--stills 1,5,12` renders preview stills instead. |

Structure (official Space Apps template):

| Time | Section | What is on screen |
|---|---|---|
| 0:00 | Team | Earth from orbit |
| 0:02 | Challenge | Dive into Fallon, Nevada; NASA POWER heat days 26 → 50 a year |
| 0:05 | Title | The field outline draws itself; FieldShift |
| 0:10 | How it works | AI field outline and Sentinel-2 zones · this week + "Why?" · rotation plan + impact |
| 0:20 | Future vision | Every farm on Earth, six languages · the globe with the four demo fields · next steps |
