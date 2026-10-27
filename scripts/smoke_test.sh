#!/usr/bin/env bash
# Run the API image against a RabbitMQ and check every endpoint, including a round
# trip through the queues. Something must consume invoice.jobs (a worker pod or
# scripts/fake_worker.py).
# Usage: RABBITMQ_URL=amqp://... scripts/smoke_test.sh [image] [port]
set -euo pipefail

IMAGE="${1:-invoiceai-api:local}"
PORT="${2:-5000}"
RABBITMQ_URL="${RABBITMQ_URL:-amqp://guest:guest@localhost:5672/%2F}"
NAME="invoiceai-smoke-$$"
BASE="http://127.0.0.1:${PORT}"

cleanup() {
  docker logs "$NAME" > smoke-container.log 2>&1 || true
  docker rm -f "$NAME" > /dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
  echo "FAIL: $1"
  docker logs "$NAME" 2>&1 | tail -50 || true
  exit 1
}

docker run -d --name "$NAME" --network host -e RABBITMQ_URL="$RABBITMQ_URL" "$IMAGE" \
  uvicorn app:app --host 127.0.0.1 --port "$PORT" > /dev/null

for _ in $(seq 1 30); do
  curl -fsS "$BASE/health" > /dev/null 2>&1 && break
  sleep 1
done
body=$(curl -fsS "$BASE/health") || fail "/health unreachable"
[ "$body" = '{"status":"ok"}' ] || fail "/health returned $body"
echo "ok   GET /health"

pdf=$(mktemp --suffix=.pdf)
printf '%%PDF-1.4\n%%%%EOF\n' > "$pdf"

body=$(curl -fsS -F "pdfs=@${pdf};filename=gone.pdf" "$BASE/upload") || fail "/upload failed"
echo "$body" | grep -q '"uploaded":\["gone.pdf"\]' || fail "/upload returned $body"
body=$(curl -fsS -H 'Content-Type: application/json' -d '{"filename":"gone.pdf"}' "$BASE/delete") || fail "/delete failed"
echo "$body" | grep -q '"deleted":"gone.pdf"' || fail "/delete returned $body"
code=$(curl -s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' -d '{"filename":"gone.pdf"}' "$BASE/delete")
[ "$code" = "404" ] || fail "second /delete returned HTTP $code"
echo "ok   POST /upload, /delete"

curl -fsS -F "pdfs=@${pdf};filename=ui.pdf" "$BASE/upload" > /dev/null
body=$(curl -fsS -X POST --max-time 120 "$BASE/process") || fail "/process failed"
echo "$body" | grep -q '"success":true' || fail "/process returned $body"
echo "$body" | grep -q '"filename":"ui.json"' || fail "/process missing result: $body"
echo "ok   POST /process (API -> RabbitMQ -> worker -> RabbitMQ -> API)"

body=$(curl -fsS -F "pdfs=@${pdf};filename=b1.pdf" -F "pdfs=@${pdf};filename=b2.pdf" -F "pdfs=@${pdf};filename=b3.pdf" "$BASE/jobs") \
  || fail "POST /jobs failed"
job_id=$(echo "$body" | sed -n 's/.*"job_id":"\([^"]*\)".*/\1/p')
[ -n "$job_id" ] || fail "POST /jobs returned $body"
for _ in $(seq 1 60); do
  body=$(curl -fsS "$BASE/jobs/$job_id")
  echo "$body" | grep -q '"status":"done"' && break
  sleep 1
done
echo "$body" | grep -q '"done":3,"total":3' || fail "bulk job did not finish: $body"
echo "ok   POST /jobs + GET /jobs/{id} (3 PDFs)"

echo "All smoke tests passed."
