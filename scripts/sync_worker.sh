#!/usr/bin/env bash
# Copy the worker's pipeline into worker/ for the single-service build (Dockerfile.lite, INLINE_WORKER=1).
#   scripts/sync_worker.sh [git-ref]      (default: origin/worker)
# The copy is committed so hosts that build straight from this branch (Render) have it.
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
ref="${1:-origin/worker}"

rm -rf "$repo/worker"
mkdir -p "$repo/worker"
git -C "$repo" archive "$ref" worker.py ocr_pipeline.py gemini_ocr.py telemetry.py requirements-gemini.txt src \
  | tar -x -C "$repo/worker"
echo "$ref $(git -C "$repo" rev-parse --short "$ref")" > "$repo/worker/SOURCE"
echo "worker/ synced from $(cat "$repo/worker/SOURCE")"
