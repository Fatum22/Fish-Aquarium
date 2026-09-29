#!/usr/bin/env bash
# Copy the Art Director's food pack icons V1 into the game (food/, relative URLs, works under a GitHub Pages subpath).
# Repeatable: re-run whenever art/food-v1 changes, then commit food/ (bump the ?v= build id only if JS/CSS changed).
#   tools/sync_food_art.sh [SRC]   (default SRC = /workspace/studio/briefs/aquarium/art/food-v1)
# Ships food_<n>.svg (what the game draws: the whole 480x240 viewBox, contained) + thumbs/food_<n>-512.png (fallback).
set -euo pipefail
SRC="${1:-/workspace/studio/briefs/aquarium/art/food-v1}"
DST="$(cd "$(dirname "$0")/.." && pwd)/food"
SIZES="5 10 50 250 500"
mkdir -p "$DST"
for n in $SIZES; do
  svg="$SRC/food_$n.svg"; png="$SRC/thumbs/food_$n-512.png"
  [ -f "$svg" ] || { echo "missing $svg" >&2; exit 1; }
  [ -f "$png" ] || { echo "missing $png" >&2; exit 1; }
  grep -q 'viewBox="0 0 480 240"' "$svg" || { echo "$svg: viewBox is not 0 0 480 240" >&2; exit 1; }
  cp -p "$svg" "$DST/food_$n.svg"
  cp -p "$png" "$DST/food_$n-512.png"
done
echo "synced from $SRC:"
for n in $SIZES; do
  printf '  food_%-4s svg %s  %s\n' "$n" "$(date -r "$DST/food_$n.svg" '+%Y-%m-%d %H:%M:%S %Z')" "$(sha1sum "$DST/food_$n.svg" | cut -c1-10)"
done
