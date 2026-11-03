#!/usr/bin/env bash
# Send documents through a running Space (local container or deployed) and wait for every result.
#   bash huggingface/smoke_test.sh http://localhost:5000 invoice.pdf [more files...]
# Passes once each file has a result. REQUIRE_OK=1 also fails on error results (needs a working GOOGLE_API_KEY).
set -euo pipefail

url="${1:?usage: smoke_test.sh <api-url> <file>...}"; shift
[ $# -gt 0 ] || { echo "no files given"; exit 2; }
TIMEOUT="${TIMEOUT:-900}"

for i in $(seq 1 60); do
  curl -fsS "$url/health" >/dev/null 2>&1 && break
  [ "$i" = 60 ] && { echo "API never became healthy"; exit 1; }
  sleep 5
done
echo "health: $(curl -fsS "$url/health")"

args=()
for f in "$@"; do args+=(-F "files=@$f"); done
# /health doesn't check RabbitMQ, which starts a few seconds after the API; until then uploads get 503.
for i in $(seq 1 30); do
  code=$(curl -sS -o /tmp/smoke_job.json -w '%{http_code}' "${args[@]}" "$url/jobs")
  [ "$code" = 202 ] && break
  [ "$code" = 503 ] && [ "$i" -lt 30 ] || { echo "upload failed: HTTP $code $(cat /tmp/smoke_job.json)"; exit 1; }
  sleep 5
done
job=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["job_id"])' /tmp/smoke_job.json)
echo "job: $job"

deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  status=$(curl -fsS "$url/jobs/$job")
  state=$(printf '%s' "$status" | python3 -c 'import json,sys; s=json.load(sys.stdin); print(s["status"], s["progress"]["done"], s["progress"]["total"])')
  echo "$(date +%T) $state"
  [ "${state%% *}" = done ] && break
  [ "$(date +%s)" -ge "$deadline" ] && { echo "timed out"; exit 1; }
  sleep 10
done

printf '%s' "$status" | REQUIRE_OK="${REQUIRE_OK:-0}" python3 -c '
import json, os, sys
results = json.load(sys.stdin)["results"]
errors = [r for r in results if "error" in r]
for r in results:
    print(r["filename"], "ERROR: " + r["error"][:300] if "error" in r else "OK: " + json.dumps(r)[:300])
if errors and os.environ["REQUIRE_OK"] == "1":
    sys.exit(f"{len(errors)} file(s) failed")
'
