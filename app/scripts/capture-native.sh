#!/usr/bin/env bash
# Re-runnable native build + capture for media/. Usage (from repo root, API running on :8000):
#   app/scripts/capture-native.sh ios        # Release simulator build with capture tour, screenshots + video
#   app/scripts/capture-native.sh android    # needs app/build-artifacts/fieldshift-v1.0.0-capture.apk
#                                            #   (CAPTURE=1 app/scripts/build-android-remote.sh) and a booted emulator
#   app/scripts/capture-native.sh ios-release   # normal Release simulator build (no tour) installed for manual use
# The capture tour (src/lib/captureTour.tsx) is timing-based; screenshot offsets below match its step timings.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/app"; MEDIA="$ROOT/media"; TMP=${TMPDIR:-/tmp}/fieldshift-capture; mkdir -p "$TMP"
# offsets (s after launch) -> screenshot name
SHOTS=("4:onboarding" "16:home-today" "30:home-replay" "39:why" "69:rotations" "89:whatif" "101:climate")
TOTAL=105

ios_udid() {
  local u; u=$(xcrun simctl list devices | grep -E "FieldShift iPhone 17 \(iOS 27\).*Booted|FieldShift iPhone 17 \(iOS 27\)" | head -1 | grep -oE "[0-9A-F-]{36}" || true)
  if [ -z "$u" ]; then u=$(xcrun simctl create "FieldShift iPhone 17 (iOS 27)" com.apple.CoreSimulator.SimDeviceType.iPhone-17 com.apple.CoreSimulator.SimRuntime.iOS-27-0); fi
  xcrun simctl boot "$u" 2>/dev/null || true; xcrun simctl bootstatus "$u" -b >/dev/null; echo "$u"
}

ios_build() { # $1 = 1 for capture tour
  cd "$APP"
  [ -d ios ] || { CI=1 npx expo prebuild -p ios --no-install && (cd ios && pod install); }
  local u; u=$(ios_udid)
  (cd ios && EXPO_PUBLIC_CAPTURE_TOUR="$1" xcodebuild -workspace FieldShift.xcworkspace -scheme FieldShift -configuration Release \
     -sdk iphonesimulator -destination "id=$u" -derivedDataPath build CODE_SIGNING_ALLOWED=NO -quiet)
  xcrun simctl uninstall "$u" org.fieldshift.app || true
  xcrun simctl install "$u" ios/build/Build/Products/Release-iphonesimulator/FieldShift.app
  echo "$u"
}

compress() { # raw -> media/<name>.mp4, sped up 2.5x to ~40 s, 720 px wide
  ffmpeg -y -loglevel error -i "$1" -filter:v "setpts=PTS/2.5,scale=720:-2,fps=30" -an -c:v libx264 -crf 28 -preset slow -pix_fmt yuv420p "$MEDIA/$2.mp4"
}

case "${1:-}" in
ios)
  u=$(ios_build 1 | tail -1)
  # fresh boot: clears any leftover system dialogs (e.g. from earlier simctl openurl calls)
  xcrun simctl shutdown "$u" || true; xcrun simctl boot "$u"; xcrun simctl bootstatus "$u" -b >/dev/null; sleep 25
  xcrun simctl status_bar "$u" override --time "9:41" --batteryState charged --batteryLevel 100 --wifiBars 3 || true
  xcrun simctl io "$u" recordVideo --codec=h264 --force "$TMP/ios-raw.mp4" >/dev/null 2>&1 & REC=$!
  sleep 2
  for i in $(seq 1 12); do xcrun simctl launch "$u" org.fieldshift.app >/dev/null 2>&1 && break; sleep 5; done
  t0=$(date +%s)
  for s in "${SHOTS[@]}"; do off=${s%%:*}; name=${s#*:}
    while [ $(( $(date +%s) - t0 )) -lt "$off" ]; do sleep 0.5; done
    xcrun simctl io "$u" screenshot "$MEDIA/ios-$name.png" >/dev/null 2>&1; echo "ios-$name.png"; done
  while [ $(( $(date +%s) - t0 )) -lt "$TOTAL" ]; do sleep 0.5; done
  kill -INT $REC; wait $REC 2>/dev/null || true; compress "$TMP/ios-raw.mp4" ios-flow
  # leave a normal (no-tour) build installed afterwards
  ios_build 0 >/dev/null; echo "iOS capture done" ;;
ios-release) ios_build 0 ;;
android)
  export ANDROID_HOME=${ANDROID_HOME:-$HOME/Library/Android/sdk}; ADB=$ANDROID_HOME/platform-tools/adb
  APK=${APK:-$APP/build-artifacts/fieldshift-v1.0.0-capture.apk}
  $ADB wait-for-device; $ADB uninstall org.fieldshift.app >/dev/null 2>&1 || true; $ADB install -r "$APK" >/dev/null
  $ADB shell settings put global hide_error_dialogs 1 || true   # no ANR popups over captures (slow cold start on emulator)
  $ADB shell settings put global sysui_demo_allowed 1 || true
  $ADB shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941 >/dev/null || true
  $ADB shell screenrecord --time-limit 180 --bit-rate 6000000 /sdcard/fs-flow.mp4 & REC=$!
  sleep 2; $ADB shell am start -W -n org.fieldshift.app/.MainActivity >/dev/null; t0=$(date +%s)
  for s in "${SHOTS[@]}"; do off=${s%%:*}; name=${s#*:}
    while [ $(( $(date +%s) - t0 )) -lt "$off" ]; do sleep 0.5; done
    $ADB exec-out screencap -p > "$MEDIA/android-$name.png"; echo "android-$name.png"; done
  while [ $(( $(date +%s) - t0 )) -lt "$TOTAL" ]; do sleep 0.5; done
  $ADB shell pkill -INT screenrecord || kill -INT $REC || true; sleep 3; $ADB pull /sdcard/fs-flow.mp4 "$TMP/android-raw.mp4" >/dev/null
  compress "$TMP/android-raw.mp4" android-flow; echo "Android capture done" ;;
*) echo "usage: $0 ios|ios-release|android"; exit 2 ;;
esac
