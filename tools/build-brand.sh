#!/usr/bin/env bash
# Regenerates every brand asset (app icon and banner, store images, website, Home
# Assistant brand folder) from brand/build.py. Needs only Docker.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
docker build -q -t pleatview-brand tools/brand > /dev/null
docker run --rm --user "$(id -u):$(id -g)" -v "$root:/src" pleatview-brand python brand/build.py
