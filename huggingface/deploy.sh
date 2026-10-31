#!/usr/bin/env bash
# Build the Hugging Face Space from the fastapi and worker branches and push it.
#   HF_TOKEN=hf_... HF_SPACE=<user>/<space> bash huggingface/deploy.sh
# HF_TOKEN needs write access (huggingface.co/settings/tokens). Run it again after changing either branch.
# Only code goes up: Spaces reject binary files pushed without LFS, so data/, output/ etc. stay behind.
set -euo pipefail

: "${HF_TOKEN:?set HF_TOKEN}"
: "${HF_SPACE:?set HF_SPACE=<user>/<space>}"
API_REF="${API_REF:-origin/fastapi}"
WORKER_REF="${WORKER_REF:-origin/worker}"

here="$(cd "$(dirname "$0")" && pwd)"
git -C "$here" fetch -q origin
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

cp -r "$here/space/." "$build/"
mkdir -p "$build/api" "$build/worker"
git -C "$here" archive "$API_REF" app.py broker.py job_store.py metrics.py object_store.py queues.py requirements.txt \
  | tar -x -C "$build/api"
# telemetry.py is imported by worker.py (the worker branch's own Dockerfile misses it).
git -C "$here" archive "$WORKER_REF" worker.py ocr_pipeline.py telemetry.py setup.py requirements.txt src \
  | tar -x -C "$build/worker"

cd "$build"
git init -q -b main
git add -A
git -c user.name=deploy -c user.email=deploy@localhost commit -qm "Deploy $(git -C "$here" rev-parse --short "$API_REF") / $(git -C "$here" rev-parse --short "$WORKER_REF")"
# The Space is a build target, not a source repo: replace whatever is there.
git push -f "https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" main
echo "Pushed. Build logs: https://huggingface.co/spaces/${HF_SPACE}?logs=build"
echo "API URL:          https://${HF_SPACE/\//-}.hf.space"
