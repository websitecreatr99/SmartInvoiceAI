#!/usr/bin/env bash
# Assemble the Space's files into a directory: space/ plus the code from the fastapi and worker branches.
#   bash huggingface/build.sh <out-dir>
# Used by deploy.sh and the Space test workflow. Only code is copied: Spaces reject binary files pushed
# without LFS, so data/, output/ etc. stay behind.
set -euo pipefail

out="${1:?usage: build.sh <out-dir>}"
API_REF="${API_REF:-origin/fastapi}"
WORKER_REF="${WORKER_REF:-origin/worker}"
here="$(cd "$(dirname "$0")" && pwd)"
root="$(git -C "$here" rev-parse --show-toplevel)"

mkdir -p "$out/api" "$out/worker"
cp -r "$here/space/." "$out/"
git -C "$root" archive "$API_REF" app.py broker.py job_store.py metrics.py object_store.py queues.py requirements.txt \
  | tar -x -C "$out/api"
# telemetry.py is imported by worker.py (the worker branch's own Dockerfile misses it).
git -C "$root" archive "$WORKER_REF" worker.py ocr_pipeline.py telemetry.py setup.py requirements.txt src \
  | tar -x -C "$out/worker"
