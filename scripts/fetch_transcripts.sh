#!/usr/bin/env bash
# Fetches the demo transcript corpus for The Lenny Growth Assistant.
#
# Source: the official free starter pack published by Lenny's Newsletter
#   https://github.com/LennysNewsletter/lennys-newsletterpodcastdata
# License: personal / non-commercial use, no redistribution of raw files.
# That's why this script *fetches* the data at setup time instead of the repo
# vendoring copies of the transcripts. See data/README.md for details.
set -euo pipefail

REPO_URL="https://github.com/LennysNewsletter/lennys-newsletterpodcastdata.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
TRANSCRIPTS_DIR="$DATA_DIR/transcripts"
TMP_DIR="$(mktemp -d)"

# Curated growth/PM demo corpus (10 episodes). Pass --all to pull every
# episode in the free starter pack (50 episodes) instead.
CURATED=(
  amol-avasare
  brian-halligan
  elena-verna-40
  evan-spiegel
  grant-lee
  jason-cohen
  jason-m-lemkin
  mark-pincus
  nikhyl-singhal-2
  stewart-butterfield
)

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "Cloning $REPO_URL (shallow)..."
git clone --depth 1 --quiet "$REPO_URL" "$TMP_DIR"

mkdir -p "$TRANSCRIPTS_DIR"

if [[ "${1:-}" == "--all" ]]; then
  echo "Copying all podcast transcripts..."
  cp "$TMP_DIR"/podcasts/*.md "$TRANSCRIPTS_DIR/"
else
  echo "Copying curated growth/PM subset (${#CURATED[@]} episodes)..."
  for slug in "${CURATED[@]}"; do
    cp "$TMP_DIR/podcasts/$slug.md" "$TRANSCRIPTS_DIR/$slug.md"
  done
fi

count=$(find "$TRANSCRIPTS_DIR" -name '*.md' | wc -l)
echo "Done. $count transcript(s) in $TRANSCRIPTS_DIR"
echo "Next: cd backend && python scripts/ingest.py"
