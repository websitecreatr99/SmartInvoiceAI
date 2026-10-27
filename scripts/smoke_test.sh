#!/usr/bin/env bash
# Start the API image and exercise every endpoint against the running container.
# Usage: scripts/smoke_test.sh [image] [port]
set -euo pipefail

IMAGE="${1:-invoiceai-api:local}"
PORT="${2:-5000}"
NAME="invoiceai-smoke-$$"
BASE="http://127.0.0.1:${PORT}"

cleanup() {
  docker logs "$NAME" > smoke-container.log 2>&1 || true
  docker rm -f "$NAME" > /dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
  echo "FAIL: $1"
  echo "--- container logs ---"
  docker logs "$NAME" 2>&1 | tail -50 || true
  exit 1
}

docker run -d --name "$NAME" -p "${PORT}:5000" "$IMAGE" > /dev/null

echo "Waiting for container to become healthy..."
for _ in $(seq 1 30); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo starting)
  [ "$status" = "healthy" ] && break
  [ "$status" = "unhealthy" ] && fail "container reported unhealthy"
  sleep 2
done
[ "$status" = "healthy" ] || fail "container did not become healthy in time"
echo "ok   container healthy"

body=$(curl -fsS "$BASE/health") || fail "/health request failed"
[ "$body" = '{"status":"ok"}' ] || fail "/health returned $body"
echo "ok   GET /health"

pdf=$(mktemp --suffix=.pdf)
printf '%%PDF-1.4\n%%%%EOF\n' > "$pdf"
body=$(curl -fsS -F "pdfs=@${pdf};filename=smoke.pdf" "$BASE/upload") || fail "/upload request failed"
echo "$body" | grep -q '"uploaded":\["smoke.pdf"\]' || fail "/upload returned $body"
echo "ok   POST /upload"

body=$(curl -fsS -H 'Content-Type: application/json' -d '{"filename":"smoke.pdf"}' "$BASE/delete") || fail "/delete request failed"
echo "$body" | grep -q '"deleted":"smoke.pdf"' || fail "/delete returned $body"
echo "ok   POST /delete"

code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -d '{"filename":"missing.pdf"}' "$BASE/delete")
[ "$code" = "404" ] || fail "/delete of missing file returned HTTP $code"
echo "ok   POST /delete (missing -> 404)"

# Runs the real ocr_pipeline.py inside the container, which proves its imports
# (PaddleOCR, LangChain, OpenCV) resolve. No OCR text exists yet, so no LLM call is made.
body=$(curl -fsS -X POST --max-time 300 "$BASE/process") || fail "/process request failed"
echo "$body" | grep -q '"success":true' || fail "/process returned $body"
echo "ok   POST /process"

echo "All smoke tests passed."
