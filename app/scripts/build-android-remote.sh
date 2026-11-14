#!/usr/bin/env bash
# Build the Android release APK on the Linux data box (fast internet; the Mac's link is too slow for
# the ~1 GB NDK). Copies the current app/ working tree (no git push needed), installs JDK 17 + Android
# SDK/NDK in ~/android-build on first run, runs Gradle, and copies the APK back to $OUT.
#   CAPTURE=1 app/scripts/build-android-remote.sh   -> APK with the scripted capture tour baked in
#   app/scripts/build-android-remote.sh             -> normal release APK
set -euo pipefail
HOST=${HOST:-fsvps}
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT=${OUT:-$APP_DIR/build-artifacts}
NAME=${NAME:-fieldshift-v1.0.0$([ "${CAPTURE:-0}" = 1 ] && echo -capture).apk}
mkdir -p "$OUT"
ssh "$HOST" mkdir -p android-build
rsync -az --delete --exclude node_modules --exclude ios --exclude android --exclude dist --exclude build-artifacts \
  --exclude .expo "$APP_DIR/" "$HOST:android-build/app/"
ssh "$HOST" CAPTURE="${CAPTURE:-0}" bash -s <<'REMOTE'
set -euo pipefail
B=$HOME/android-build; cd "$B"
if [ ! -x jdk/bin/java ]; then
  curl -sSL -o jdk.tgz "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
  mkdir -p jdk && tar -xzf jdk.tgz -C jdk --strip-components=1 && rm jdk.tgz
fi
export JAVA_HOME=$B/jdk ANDROID_HOME=$B/sdk PATH=$B/jdk/bin:$PATH
if [ ! -x sdk/cmdline-tools/latest/bin/sdkmanager ]; then
  curl -sSL -o clt.zip https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip
  mkdir -p sdk/cmdline-tools && unzip -q -o clt.zip -d sdk/cmdline-tools && mv sdk/cmdline-tools/cmdline-tools sdk/cmdline-tools/latest && rm clt.zip
  yes | sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=sdk --licenses >/dev/null || true
fi
cd app
npm ci --no-audit --no-fund --loglevel=error
if [ "$CAPTURE" = 1 ]; then export EXPO_PUBLIC_CAPTURE_TOUR=1; else unset EXPO_PUBLIC_CAPTURE_TOUR || true; fi
CI=1 npx expo prebuild -p android --clean --no-install >/dev/null
echo "sdk.dir=$ANDROID_HOME" > android/local.properties
cd android && ./gradlew assembleRelease --no-daemon -q -PreactNativeArchitectures=arm64-v8a,x86_64 2>&1 | grep -vE "^w:|warning" | tail -20
ls -la app/build/outputs/apk/release/
REMOTE
scp "$HOST:android-build/app/android/app/build/outputs/apk/release/app-release.apk" "$OUT/$NAME"
ls -la "$OUT/$NAME"
