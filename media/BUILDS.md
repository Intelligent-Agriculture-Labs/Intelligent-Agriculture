# Native builds & media captures

Everything here can be re-run with two scripts:
- `app/scripts/capture-native.sh`: iOS build plus captures on the Mac, and Android captures on the local emulator.
- `app/scripts/build-android-remote.sh`: builds the Android APK on the Linux processing host.

Prerequisite: the IA API must be running on the Mac at `:8000`:
```
cd backend && nohup .venv/bin/uvicorn fieldshift.main:app --host 0.0.0.0 --port 8000 &
```
iOS reaches it at `localhost:8000`; Android reaches it at `10.0.2.2:8000`. Both are the app's built-in defaults; ATS and cleartext HTTP are allowed in `app.json`.

## Versions (2026-11-14)
| | |
|---|---|
| Expo SDK | 58 (`expo ~58.0.25`), React Native 0.88.1, React 19.3, expo-router 58 |
| iOS | Xcode 27.0 beta (`~/Downloads/Xcode-beta.app`), CocoaPods 1.17, simulator **iPhone 17, iOS 27.0** (24A5380i) |
| Android | compileSdk from Expo SDK 58 template (platform `android-37.0` installed on the build box), NDK 27.1.12297006, JDK 17 (Temurin 17.0.21 on the build box), Gradle 9.4.1; emulator AVD `fieldshift_pixel` = Pixel 7, Android 15 (API 35) Google APIs arm64 |

## iOS (Simulator)
```
app/scripts/capture-native.sh ios           # Release build WITH capture tour -> screenshots + video, then reinstalls a normal build
app/scripts/capture-native.sh ios-release   # just a normal Release simulator build, installed on the simulator
```
What the script does:
1. `expo prebuild -p ios` + `pod install`, only on first run (`ios/` is generated and gitignored).
2. `xcodebuild -workspace ios/IA.xcworkspace -scheme IA` (older prebuilds: `IA.xcworkspace` / `-scheme IA`) ` -configuration Release -sdk iphonesimulator -derivedDataPath ios/build CODE_SIGNING_ALLOWED=NO`. The JS is bundled into the app, so there is no Metro and no dev overlay.
3. `simctl install`, a fresh simulator boot, a status-bar override to 9:41, `simctl io recordVideo`, then app launch and timed `simctl io screenshot`.

- Artifact: `app/ios/build/Build/Products/Release-iphonesimulator/IA.app` (older prebuilds: `IA.app`) (~81 MB, simulator-only and not committed).
- Verified on iOS 27 with live NASA data from the local API. The whole core flow works: onboarding → Fallon preset → This week (today) → Replay 15 Jul 2025 (irrigation + drought cards) → Why? → Rotations → What if? → Climate.

## Android (emulator / APK)
```
CAPTURE=1 app/scripts/build-android-remote.sh   # -> app/build-artifacts/fieldshift-v1.0.0-capture.apk (tour build, for media)
app/scripts/build-android-remote.sh             # -> app/build-artifacts/fieldshift-v1.0.0.apk (normal release APK)
app/scripts/capture-native.sh android           # installs the capture APK on the running emulator, screenshots + video
```
The optional remote-build script runs on a Linux build host. Configure its SSH target and build directory for your environment before use. For a local build, use the Android commands in [deployment](../docs/DEPLOYMENT.md).
1. The script rsyncs the current `app/` working tree (no git push needed) to `~/android-build/app`.
2. First run only: it installs Temurin JDK 17 and the Android cmdline-tools into `~/android-build`. Gradle installs the NDK, CMake and platforms automatically.
3. It runs `npm ci`, `expo prebuild -p android --clean`, then `./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a,x86_64`.
4. It copies the APK back.

The release APK is signed with the template debug keystore, which is fine for emulators and sideloading but not for Play Store upload.

- Artifacts: the APKs are ~57 MB, gitignored (`*.apk`, `app/build-artifacts/`), and kept in `app/build-artifacts/`.
- Emulator: `emulator -avd fieldshift_pixel -no-snapshot -no-audio -gpu host`. With `-gpu swiftshader_indirect` the slow cold start raised ANR dialogs, so the script also sets `settings put global hide_error_dialogs 1`.
- Verified on Android 15 (API 35) with live NASA data from the local API (via `10.0.2.2`): the same core flow as iOS.

## Captures in this folder
| File | Content |
|---|---|
| `ios-onboarding.png`, `android-onboarding.png` | Onboarding with demo farms and map |
| `ios-home-today.png`, `android-home-today.png` | Fallon, today (mid-November: no irrigation needed / off-season) |
| `ios-home-replay.png`, `android-home-replay.png` | Replay 15 Jul 2025: "Irrigate … mm by Sun 20" + moderate drought (D1) |
| `ios-why.png`, `android-why.png` | Why? view of the irrigation card (reasoning steps, data) |
| `ios-rotations.png`, `android-rotations.png` | Rotation explorer (current rotation + priorities) |
| `ios-whatif.png`, `android-whatif.png` | What-if simulator inputs |
| `ios-climate.png`, `android-climate.png` | Climate trends since 1984 (NASA POWER) |
| `ios-flow.mp4`, `android-flow.mp4` | Whole tour, sped up 2.5× (≈42 s iOS / ≈64 s Android incl. the slower emulator cold start), 720 px, H.264, no audio |
| `web-*.png`, `web-replay-*.png` | Web captures (Playwright: `app/e2e/screenshots.ts`, `app/e2e/screenshots-replay.ts`) |

## How the UI is driven (and why not Maestro/XCUITest)
- `app/e2e/maestro/core-flow.yaml` is the mobile E2E flow (Maestro 2.12.1 installed in `~/.maestro/maestro/bin`). With the tested Xcode 27 beta toolchain, the **XCUITest runner hangs** ("test runner hung before establishing connection", DTServiceHub/lockdown errors on both the iOS 26.4 and iOS 27.0 runtimes). Use a stable Xcode version for Maestro iOS automation, or run it on Android (`maestro test app/e2e/maestro/core-flow.yaml -e PLATFORM=android`).
- `simctl openurl` deep links (`fieldshift://onboarding?preset=fallon_nv&replay=1`, handled in `onboarding.tsx`) trigger a system "Open in IA?" confirmation that can't be dismissed headlessly (this Xcode beta has no Simulator.app GUI).
- So captures use a **capture tour**: builds made with `EXPO_PUBLIC_CAPTURE_TOUR=1` run a scripted, timing-based walk through the screens (`app/src/lib/captureTour.tsx`), and the script takes screenshots at matching offsets. Normal builds never contain the tour (the flag is inlined at bundle time).
- To change the steps or their timings, edit `captureTour.tsx` and the `SHOTS` offsets in `capture-native.sh` together.
- Known limitation: screenshots show the top of each screen only; the tour doesn't scroll, so rotation strategy cards and What-if results are below the fold.
