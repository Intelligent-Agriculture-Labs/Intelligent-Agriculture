# FieldShift app (web · iOS · Android)

One Expo (SDK 58) + expo-router + TypeScript codebase. The web build uses react-native-web.

## Run

```bash
npm install
EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start      # press w / i / a
npm run export:web && npx serve -s dist -l 4173               # static web build
npx expo run:ios    # iOS Simulator (dev build; needs Xcode + CocoaPods)
npx expo run:android  # Android emulator; API defaults to http://10.0.2.2:8000
```

| Env var                    | Default                                                       | Purpose                                |
| -------------------------- | ------------------------------------------------------------- | -------------------------------------- |
| `EXPO_PUBLIC_API_URL`      | same origin; `:8000` in local dev; `10.0.2.2:8000` on Android | FieldShift API base URL                |
| `EXPO_PUBLIC_DOCS_URL`     | GitHub `docs/MODELS.md`                                       | "Methodology" links                    |
| `EXPO_PUBLIC_DISABLE_MOCK` | unset                                                         | `1` = never fall back to MOCK fixtures |

## Data origin & offline

Every response is `live` → `cache` (last good answer stored on the device, shown with an **Offline** banner) →
`mock` (bundled `src/api/__fixtures__/MOCK_*.json`, shown with a red **MOCK DATA** banner). Mock data is never shown silently.

## Structure

- `src/app/` – routes: `onboarding`, `(tabs)/home|rotations|whatif|climate|settings`, `why/[cardId]`
- `src/api/` – `types.ts` (copy of `../contracts/api.ts`), `client.ts` (fetch + fallback chain)
- `src/components/` – UI primitives, SVG charts, map picker (`MapPicker.web.tsx` iframe / `MapPicker.tsx` WebView, shared Leaflet page with NASA GIBS MODIS layers)
- `src/i18n/locales/` – en, es, fr, sw, hi, de (add a JSON file + register it in `src/i18n/index.ts`)

## Quality

```bash
npm run lint && npm run typecheck && npm test          # eslint, tsc, jest (units, i18n completeness, chart ticks)
npm run export:web && npx playwright test              # e2e core flow (desktop + Pixel 7)
node --experimental-strip-types e2e/screenshots.ts     # refresh ../media/web-*.png
```
