# Deployment

## One command (any OS with Docker)
```bash
git clone <repo> fieldshift && cd fieldshift
docker compose up --build
# web app  → http://localhost:8080
# API docs → http://localhost:8080/docs   (one container: FastAPI serves the API and the exported web app)
```
Fully offline demo (pre-cached NASA data for the four demo farms; no network calls at all):
```bash
FIELDSHIFT_OFFLINE=1 docker compose up --build
```

| Variable | Default | Meaning |
|---|---|---|
| `FIELDSHIFT_OFFLINE` | `0` | `1` = never call the network |
| `FIELDSHIFT_CACHE_DIR` | `/data/cache` (container) | response cache (volume `cache`) |
| `FIELDSHIFT_ORNL_RETRIES` | `1` | retries for the slow ORNL subset API |
| `FIELDSHIFT_CIRCUIT_BREAKER` | `1` | skip a hanging host for 5 min |
| `EXPO_PUBLIC_API_URL` | same origin | client → API base URL (build time) |
| `PORT` | `8080` | host port of the container |
| `FIELDSHIFT_WEB_DIR` | `/srv/web` (image) | serve the exported web app from this folder |

No secrets are needed. `.env.example` lists the optional ones.

## Without Docker
See DEV_ENVIRONMENT.md (uv + uvicorn for the backend; `npx expo start` for the client).

## Mobile builds
- **iOS (macOS + Xcode):** `cd app && npx expo prebuild -p ios && npx expo run:ios --configuration Release`.
- **Android:** `cd app && npx expo prebuild -p android && cd android && ./gradlew assembleRelease`.
- **Store builds:** EAS (`npx eas-cli build`) with your own Apple/Google accounts. Not done in the hackathon.
- Exact commands and versions used: media/BUILDS.md.

## Public hosting (human step)
The images are host-agnostic: any VM with Docker works, as do Fly.io, Render or Railway. On the team's VPS:
```bash
ssh fsvps 'cd ~/fieldshift && git pull && PORT=8090 podman-compose up -d --build'
```
Then expose port 8080 through a reverse proxy or a tunnel (e.g. Tailscale Funnel or Cloudflare Tunnel). Making it public is left to the owner, because it opens the machine to the internet.

## Windows
Docker Desktop (WSL 2 backend): run `docker compose up --build` from PowerShell or WSL in the repo folder. For backend development without Docker, use WSL (Ubuntu) and follow the Linux steps. Native Windows also works with `uv venv` and `.venv\Scripts\uvicorn`.

## Verification log
| Date (CET) | Platform | Command | Result |
|---|---|---|---|
| 2026-11-14 20:15 | Windows 11 (SALE), native | `uv venv --python 3.13` + `pytest`, `ruff`, `mypy`; `npm ci`, `tsc`, `jest` | 47/47 backend, lint/types clean; 39/39 client tests |
| 2026-11-14 20:15 | Windows 11 (SALE), WSL Fedora 43 (Python 3.14) | `python3 -m venv` + `pytest` | 47/47 |
| 2026-11-14 20:15 | Windows 11 (SALE), Podman as `docker` | `docker compose build` | Failed: npm downloads timed out inside Podman's build network (the same `npm ci` works on the host). Mitigated with npm fetch retries/timeouts in the Dockerfile; see Troubleshooting |
| 2026-11-14 19:40 | Linux (Fedora, podman 5.8 + podman-compose) | `FIELDSHIFT_OFFLINE=1 PORT=8090 podman-compose up -d --build` | Image built; `/api/health` → `offline_mode: true`; web app 200; `/api/advice` for the Fallon field answered from the bundled demo cache |
| 2026-11-14 18:12 | Linux (Fedora, podman) | `PORT=8090 podman-compose up -d` (live mode) | Web app, deep links, `/docs`, advice OK |
| 2026-11-14 19:45 | macOS (Apple Silicon) | Dev setup: `uv` venv + `uvicorn`; `npx expo export -p web`; Playwright E2E | 47 backend tests, 39 client unit tests, 14/14 E2E (desktop + Pixel 7) |
| 2026-11-14 19:30 | iOS Simulator (Xcode 27 beta, iOS 27) | `app/scripts/capture-native.sh ios` | Release build runs the full tour; 11 screenshots + flow video |
| 2026-11-14 19:35 | Android emulator (API 35) | `CAPTURE=1 app/scripts/build-android-remote.sh && app/scripts/capture-native.sh android` | APK built on the VPS; full tour on the emulator; 11 screenshots + flow video |

## Troubleshooting
- **`npm error Exit handler never called!` / `ETIMEDOUT` during `docker compose build`:** package downloads time out inside the container build network (seen with Podman on Windows). The Dockerfile already retries with long timeouts. If it still fails:
  - check the Podman machine's DNS/proxy settings; or
  - build on a machine with Docker Desktop; or
  - run without containers (DEV_ENVIRONMENT.md: `uv` + `uvicorn`, then `npx expo export -p web` and set `FIELDSHIFT_WEB_DIR=app/dist`).
- **Python version:** the project targets 3.13 (`uv venv --python 3.13` downloads it). The tests also pass on 3.14.
