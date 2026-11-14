#!/usr/bin/env bash
# iPhone screenshots for the film and README: Release build with the "film" capture tour
# (src/lib/captureTour.tsx). The app logs "[shot] <name>" once a screen has loaded real data;
# this script screenshots at that moment -> media/iphone-<name>.png (iPhone 17, 1206 x 2622).
# Usage (repo root, API on :8000): app/scripts/capture-film-ios.sh   (SKIP_BUILD=1 reuses the installed build)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; APP="$ROOT/app"; MEDIA="$ROOT/media"
NAME="FieldShift Film iPhone 17"
xcrun simctl shutdown all 2>/dev/null || true
U=$(xcrun simctl list devices | grep "$NAME (" | grep -oE "[0-9A-F-]{36}" | head -1 || true)
[ -n "$U" ] || U=$(xcrun simctl create "$NAME" com.apple.CoreSimulator.SimDeviceType.iPhone-17 com.apple.CoreSimulator.SimRuntime.iOS-27-0)
xcrun simctl boot "$U" 2>/dev/null || true; xcrun simctl bootstatus "$U" -b >/dev/null
cd "$APP/ios"
if [ "${SKIP_BUILD:-0}" != 1 ]; then
EXPO_PUBLIC_CAPTURE_TOUR=film xcodebuild -workspace FieldShift.xcworkspace -scheme FieldShift -configuration Release \
  -sdk iphonesimulator -destination "id=$U" -derivedDataPath build CODE_SIGNING_ALLOWED=NO -quiet
xcrun simctl uninstall "$U" org.fieldshift.app 2>/dev/null || true
xcrun simctl install "$U" build/Build/Products/Release-iphonesimulator/FieldShift.app
fi
xcrun simctl terminate "$U" org.fieldshift.app 2>/dev/null || true
xcrun simctl status_bar "$U" override --time "9:41" --batteryState charged --batteryLevel 100 --wifiBars 3 --cellularBars 4 || true
LOG=$(mktemp); xcrun simctl spawn "$U" log stream --level info --style compact --predicate 'eventMessage CONTAINS "[shot]"' > "$LOG" 2>/dev/null & LS=$!
sleep 3; xcrun simctl launch "$U" org.fieldshift.app >/dev/null
seen=""; t0=$(date +%s)
while [ $(( $(date +%s) - t0 )) -lt 600 ]; do
  for name in $(grep -oE "\[shot\] [a-z0-9-]+" "$LOG" | awk '{print $2}'); do
    case " $seen " in *" $name "*) continue ;; esac
    seen="$seen $name"
    [ "$name" = done ] && break 2
    xcrun simctl io "$U" screenshot "$MEDIA/iphone-$name.png" >/dev/null 2>&1 && echo "iphone-$name.png"
  done
  sleep 0.3
done
kill $LS 2>/dev/null || true; rm -f "$LOG"
echo "film capture done"
