#!/usr/bin/env bash
# Puts an end-to-end run's pictures (tools/e2e/run.py --screens) on the website, as WebP.
#
#   tools/site-screens.sh tools/e2e/out/<time>/screens
#
# The full-size PNGs stay in the run's folder for the stores.
set -euo pipefail
src=$(realpath "${1:?usage: tools/site-screens.sh tools/e2e/out/<time>/screens}")
dest=$(realpath "$(dirname "$0")/../site/img")/screens
mkdir -p "$dest"
docker run --rm --user "$(id -u):$(id -g)" -v "$src:/in:ro" -v "$dest:/out" --entrypoint python3 \
  ghcr.io/home-assistant/home-assistant:stable -c '
from pathlib import Path
from PIL import Image
for png in sorted(Path("/in").glob("*.png")):
    target = Path("/out") / f"{png.stem}.webp"
    Image.open(png).convert("RGB").save(target, "WEBP", quality=82, method=6)
    print(f"{target.name}: {target.stat().st_size // 1024} KB")
'
