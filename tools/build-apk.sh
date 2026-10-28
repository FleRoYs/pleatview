#!/usr/bin/env bash
# Builds the PleatView APK inside Docker, so no local Android SDK is needed.
#
#   tools/build-apk.sh                 # debug APK + unit tests
#   tools/build-apk.sh assembleRelease # any Gradle tasks
#
# Output: android/app/build/outputs/apk/<variant>/
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
image="pleatview-android-build"
tasks=("$@")
[ ${#tasks[@]} -eq 0 ] && tasks=(testDebugUnitTest assembleDebug)

docker build -q -t "$image" "$root/tools/android-build" > /dev/null
# ~/.android holds the debug signing key; keeping it means new builds can update an
# installed APK (a different key forces an uninstall, which wipes pairing and settings).
mkdir -p "$HOME/.gradle" "$HOME/.android"

exec docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/home -e GRADLE_USER_HOME=/gradle -e ANDROID_USER_HOME=/tmp/home/.android \
  -e PLEATVIEW_KEYSTORE -e PLEATVIEW_KEYSTORE_PASSWORD -e PLEATVIEW_KEY_ALIAS -e PLEATVIEW_KEY_PASSWORD \
  -v "$HOME/.gradle:/gradle" \
  -v "$HOME/.android:/tmp/home/.android" \
  -v "$root/android:/work" \
  -w /work \
  "$image" ./gradlew --no-daemon --console=plain "${tasks[@]}"
