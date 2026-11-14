# Development environment

| Machine | Role | Access (verified 2026-11-14) |
|---|---|---|
| macOS laptop (this machine, Apple Silicon) | Main editing, iOS build (Xcode beta, iOS 26/27 simulators), Android emulator (SDK installed via Homebrew `android-commandlinetools`), Docker Desktop | local |
| `vps-home-node-1` (Fedora, 24 cores, 93 GB RAM, RTX 5070 Ti, podman) | Data processing: demo-cache precompute, validation runs; Gitea (git source of truth) | `ssh fsvps` from the Mac (Tailscale `100.106.220.63`). The key `~/.ssh/id_ed25519_fieldshift` was authorized via SALE's WSL session. |
| Windows laptop `SALE` | Gateway to the VPS (WSL), Windows dev-setup check | T3 Code linked environment `e12fcb7d-99a3-490f-935f-b1bfb199e145`. Interactive WSL can `ssh lino@vps-home-node-1`; non-interactive WSL from T3 could not use the user's key. |

## SSH config used on the Mac (`~/.ssh/config`)
```
Host fsvps
  HostName vps-home-node-1
  User lino
  IdentityFile ~/.ssh/id_ed25519_fieldshift
Host fsgitea
  HostName vps-home-node-1
  Port 2222
  User git
  IdentityFile ~/.ssh/id_ed25519_fieldshift
```

## Git
- Source of truth: Gitea `http://vps-home-node-1:3001/lino/fieldshift` (private; SSH `fsgitea:lino/fieldshift.git`).
- Clones: Mac `/Users/lino/.t3/projects/fieldshift`, VPS `~/fieldshift`. Machines sync only through git.

## Long-running jobs on the VPS
```
ssh fsvps
tmux ls                       # fs_cache = demo-cache builder, fs_val = validation
tail -f ~/fs_cache.log ~/fs_val.log
```

## Backend dev setup (any OS)
```
cd backend
uv venv --python 3.13 .venv && uv pip install -e ".[dev]"
.venv/bin/uvicorn fieldshift.main:app --reload       # http://localhost:8000/docs
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy fieldshift
```
On Windows use `.venv\Scripts\python` (or WSL, which is the recommended path; see the Windows note below).

## Client dev setup
```
cd app && npm install
npx expo start --web            # web
npx expo run:ios                # iOS simulator (macOS + Xcode)
npx expo run:android            # Android emulator (Android SDK)
```

## Windows note
The Windows/WSL check is described in docs/DEPLOYMENT.md (§Windows). `docker compose up` behaves the same under Docker Desktop on Windows.
