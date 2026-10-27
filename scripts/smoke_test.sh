#!/usr/bin/env bash
# Bring up the full stack (nginx -> API replicas -> Redis -> workers) and check it end to end.
# Usage: scripts/smoke_test.sh [port]
set -euo pipefail

PORT="${1:-8080}"
BASE="http://127.0.0.1:${PORT}"
export PORT API_REPLICAS=2 WORKER_REPLICAS=2

cleanup() {
  docker compose logs --no-color > smoke-compose.log 2>&1 || true
  docker compose down -v > /dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
  echo "FAIL: $1"
  docker compose logs --no-color --tail 40 api worker 2>&1 || true
  exit 1
}

docker compose up -d

echo "Waiting for the API behind nginx..."
for _ in $(seq 1 60); do
  curl -fsS "$BASE/health" > /dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$BASE/health" > /dev/null || fail "API never became reachable through nginx"
echo "ok   GET /health via nginx"

replicas=$(for _ in $(seq 1 20); do curl -fsS -D - -o /dev/null "$BASE/health" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-served-by"{print $2}'; done | sort -u | wc -l)
[ "$replicas" -ge 2 ] || fail "expected requests spread over 2 API replicas, saw $replicas"
echo "ok   load balanced across $replicas API replicas"

pdf=$(mktemp --suffix=.pdf)
printf '%%PDF-1.4\n%%%%EOF\n' > "$pdf"
body=$(curl -fsS -F "pdfs=@${pdf};filename=smoke.pdf" "$BASE/jobs") || fail "POST /jobs failed"
job_id=$(echo "$body" | sed -n 's/.*"job_id":"\([^"]*\)".*/\1/p')
[ -n "$job_id" ] || fail "POST /jobs returned $body"
echo "ok   POST /jobs -> $job_id"

# The PDF is a stub, so OCR fails inside the worker; reaching "done" with a per-file
# error proves a worker picked the job up, loaded the pipeline, and reported back.
for _ in $(seq 1 90); do
  body=$(curl -fsS "$BASE/jobs/$job_id")
  echo "$body" | grep -q '"status":"\(done\|failed\)"' && break
  sleep 2
done
echo "$body" | grep -q '"status":"done"' || fail "job did not finish: $body"
echo "$body" | grep -q '"filename":"smoke.json"' || fail "job finished without a result entry: $body"
echo "ok   job processed by a worker"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/jobs/00000000-0000-0000-0000-000000000000")
[ "$code" = "404" ] || fail "unknown job returned HTTP $code"
echo "ok   unknown job -> 404"

echo "All smoke tests passed."
