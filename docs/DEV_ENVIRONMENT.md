# Development environment

## Requirements

- Python 3.13 and uv for the backend.
- Node.js 22 and npm for the Expo client.
- Docker with Compose for the complete local application.
- Xcode and CocoaPods on macOS for iOS builds; Android SDK and JDK 17 for Android builds.

## Backend

```bash
cd backend
uv venv --python 3.13 .venv
uv pip install -e ".[dev]"
.venv/bin/uvicorn fieldshift.main:app --reload
```

API documentation: http://localhost:8000/docs.

```bash
.venv/bin/ruff check . ../scripts
.venv/bin/ruff format --check .
.venv/bin/mypy fieldshift
.venv/bin/pytest -q
```

On Windows, use the corresponding executables under `.venv\Scripts`, or run the Linux commands in WSL.

## Client

```bash
cd app
npm ci
npx expo start --web
```

For native development, run `npx expo run:ios` on macOS or `npx expo run:android` with the Android SDK installed. See [mobile builds](../media/BUILDS.md) for release-build and capture details.

```bash
npm run lint
npm run typecheck
npm run format:check
npm test -- --ci
npm run export:web
```

## Containers and data processing

See [deployment](DEPLOYMENT.md) for Docker and Windows setup. Validation and dataset-generation scripts are in `scripts/`; their inputs and outputs are documented in [data](DATA.md) and [validation](VALIDATION.md). Large raw datasets and credentials remain outside version control.
