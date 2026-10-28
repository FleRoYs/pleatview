#!/usr/bin/env bash
# Sets the version for the next release in both the app and the integration, and
# increments the app's versionCode (which Google Play requires to grow every upload).
#
#   tools/bump-version.sh 0.2.0
set -euo pipefail

version="${1:?usage: tools/bump-version.sh <version>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
gradle="$root/android/app/build.gradle.kts"

code=$(sed -nE 's/^ *versionCode = ([0-9]+).*/\1/p' "$gradle")
sed -i -E "s/^( *versionCode = )[0-9]+/\1$((code + 1))/; s/^( *versionName = )\"[^\"]+\"/\1\"$version\"/" "$gradle"

python3 - "$root/custom_components/pleatview/manifest.json" "$version" <<'PY'
import json
import sys

path, version = sys.argv[1:]
with open(path) as f:
    manifest = json.load(f)
manifest["version"] = version
with open(path, "w") as f:
    f.write(json.dumps(manifest, indent=2) + "\n")
PY

echo "Version $version (versionCode $((code + 1))). After merging, tag the commit: git tag v$version"
