#!/usr/bin/env bash
# Runs the Home Assistant integration tests in Docker against the Home Assistant
# version pinned by pytest-homeassistant-custom-component.
#
#   tools/test-integration.sh            # all tests
#   tools/test-integration.sh -k camera  # extra pytest arguments
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
image="pleatview-ha-test"

docker build -q -t "$image" -f "$root/tools/ha-test/Dockerfile" "$root" > /dev/null
exec docker run --rm -v "$root:/src:ro" "$image" \
  python -m pytest -p no:cacheprovider -p no:logging -q "$@"
