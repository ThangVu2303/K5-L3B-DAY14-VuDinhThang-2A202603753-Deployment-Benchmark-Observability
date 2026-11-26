#!/usr/bin/env bash
# 4 lệnh tự kiểm CP6 — chỉ in mã HTTP, không in API key.
#   BASE=https://<app>.up.railway.app AGENT_API_KEY=<key> bash smoke_test.sh
set -u
: "${BASE:?set BASE to the public URL}"
: "${AGENT_API_KEY:?set AGENT_API_KEY}"
BASE="${BASE%/}"

check() {
  local name="$1" expected="$2"; shift 2
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' "$@")
  printf '%-22s %s (expected %s) %s\n' "$name" "$code" "$expected" "$([ "$code" = "$expected" ] && echo OK || echo FAIL)"
}

echo "BASE=$BASE"
check "GET /health"          200 "$BASE/health"
check "GET /ready"           200 "$BASE/ready"
check "POST /ask (no key)"   401 -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'
check "POST /ask (with key)" 200 -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
