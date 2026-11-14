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
| 2026-11-14 19:40 | Linux (Fedora, podman 5.8 + podman-compose) | `FIELDSHIFT_OFFLINE=1 PORT=8090 podman-compose up -d --build` | Image built; `/api/health` → `offline_mode: true`; web app 200; `/api/advice` for the Fallon field answered from the bundled demo cache |
| 2026-11-14 18:12 | Linux (Fedora, podman) | `PORT=8090 podman-compose up -d` (live mode) | Web app, deep links, `/docs`, advice OK |
| 2026-11-14 19:45 | macOS (Apple Silicon) | Dev setup: `uv` venv + `uvicorn`; `npx expo export -p web`; Playwright E2E | 47 backend tests, 39 client unit tests, 14/14 E2E (desktop + Pixel 7) |
| 2026-11-14 19:30 | iOS Simulator (Xcode 27 beta, iOS 27) | `app/scripts/capture-native.sh ios` | Release build runs the full tour; 11 screenshots + flow video |
| 2026-11-14 19:35 | Android emulator (API 35) | `CAPTURE=1 app/scripts/build-android-remote.sh && app/scripts/capture-native.sh android` | APK built on the VPS; full tour on the emulator; 11 screenshots + flow video |
