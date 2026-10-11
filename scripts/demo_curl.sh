#!/usr/bin/env bash
# The three demo scenarios end to end against a running API, with curl + jq only:
#   start the check -> sign + PUT the evidence -> answer (SSE progress alongside) -> verdict,
#   then the analyst side: the case file, and REPORT_SCAM on Mrs Tan's case.
#
#   make dev                                   # API on :8000 (AUTH_DISABLED=true locally)
#   scripts/demo_curl.sh                       # all three: tan raj aisyah
#   scripts/demo_curl.sh tan                   # one scenario
#   BASE=https://<api> ADMIN_TOKEN=... scripts/demo_curl.sh   # cloud (admin token = service caller)
#
# Env: BASE (default http://localhost:8000), TOKEN (a Firebase ID token) or ADMIN_TOKEN,
#      REPORT=0 to skip the REPORT_SCAM decision, RESET=1 to call /admin/reset-demo at the end.
# Exit code 1 if a verdict is not the expected one. All data is synthetic.
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
API="$BASE/api/v1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="${REPORT:-1}"
RESET="${RESET:-0}"
command -v jq >/dev/null || { echo "jq is required (brew install jq)"; exit 2; }

AUTH=()
if [[ -n "${ADMIN_TOKEN:-}" ]]; then AUTH=(-H "X-Admin-Token: $ADMIN_TOKEN")
elif [[ -n "${TOKEN:-}" ]]; then AUTH=(-H "Authorization: Bearer $TOKEN"); fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
post() {  # post PATH JSON -> body; fails on HTTP >= 400 with the error envelope
  local out code
  out="$(curl -sS -X POST "$API$1" ${AUTH[@]+"${AUTH[@]}"} -H 'Content-Type: application/json' \
    -d "$2" -w '\n%{http_code}')"
  code="${out##*$'\n'}"; out="${out%$'\n'*}"
  if (( code >= 400 )); then echo "POST $1 -> $code $out" >&2; return 1; fi
  printf '%s' "$out"
}
get() { curl -sS --fail-with-body "$API$1" ${AUTH[@]+"${AUTH[@]}"}; }

upload() {  # upload CHECK_ID FILE CONTENT_TYPE -> the URI for evidence_uris
  local signed url
  signed="$(post /uploads/sign "$(jq -nc --arg c "$1" --arg f "$(basename "$2")" --arg t "$3" \
    '{check_id:$c, filename:$f, content_type:$t}')")" || return 1
  url="$(jq -r .upload_url <<<"$signed")"
  local headers=()
  while IFS= read -r h; do headers+=(-H "$h"); done < <(jq -r '.headers | to_entries[] | "\(.key): \(.value)"' <<<"$signed")
  curl -sS --fail-with-body -X PUT "$url" ${headers[@]+"${headers[@]}"} --data-binary "@$2" >/dev/null || return 1
  jq -r .gcs_uri <<<"$signed"
}

FAILED=0
TAN_CASE=""

scenario() {
  local key="$1" transfer answer quick file="" ctype="" pasted="" expected
  case "$key" in
    tan)
      transfer='{"customer_id":"cust_001","language":"zh","transfer":{"payee_name":"Lee Wei Investigation Acct","account_number":"123-45678-9","bank_name":"Harbour Bank","dest_type":"LOCAL_BANK","amount":8000,"currency":"SGD","note":"case 2231"}}'
      answer="他说他是金管局的官员，我的账户涉及洗钱，要我把钱转到安全账户。"; quick="政府官员"
      file="$ROOT/data/demo/tan_mas_chat.png"; ctype="image/png"; expected="RED" ;;
    raj)
      transfer='{"customer_id":"cust_002","language":"en","transfer":{"payee_name":"Ahmad Danial","account_number":"556-208417-390","bank_name":"Orchid Trust Bank","dest_type":"LOCAL_BANK","amount":450,"currency":"SGD"}}'
      answer="The recruiter says I need to top up to unlock my commission. Here is the message."
      quick="A job recruiter"; pasted="$ROOT/data/demo/raj_job_chat.txt"; expected="AMBER RED" ;;
    aisyah)
      transfer='{"customer_id":"cust_003","language":"en","transfer":{"payee_name":"Wong Kah Wai","account_number":"436-905127-318","bank_name":"Kampong Federal Bank","dest_type":"LOCAL_BANK","amount":3200,"currency":"SGD","note":"Bishan deposit"}}'
      answer="It's the deposit for the flat we're renting in Bishan. Tenancy agreement attached."
      quick="No one, it's my own payment"; file="$ROOT/data/demo/aisyah_tenancy.pdf"
      ctype="application/pdf"; expected="GREEN" ;;
    *) echo "unknown scenario $key (tan|raj|aisyah)"; exit 2 ;;
  esac

  bold "=== $key ==="
  local started check_id status
  started="$(post /checks "$transfer")"
  check_id="$(jq -r .check_id <<<"$started")"; status="$(jq -r .status <<<"$started")"
  echo "POST /checks            -> $check_id $status, txn score $(jq -r .txn_risk.score <<<"$started")"
  echo "  question: $(jq -r '.question.text // "-"' <<<"$started")"
  [[ "$status" == "CHECKIN" ]] || { echo "  (no check-in: $(jq -r .verdict <<<"$started"))"; return; }

  local uris='[]'
  if [[ -n "$file" ]]; then
    local uri
    uri="$(upload "$check_id" "$file" "$ctype")" || { echo "  ✘ evidence upload failed"; FAILED=1; return 0; }
    uris="$(jq -nc --arg u "$uri" '[$u]')"
    echo "POST /uploads/sign + PUT -> $uri"
  fi
  local body
  body="$(jq -nc --arg t "$answer" --arg q "$quick" --argjson u "$uris" \
    '{text:$t, quick_reply:$q, evidence_uris:$u}')"
  [[ -n "$pasted" ]] && body="$(jq -c --rawfile p "$pasted" '. + {pasted_text: $p}' <<<"$body")"

  # Progress events (SSE) alongside the answer, as the customer app would show them.
  curl -sSN --max-time 60 "$API/checks/$check_id/events" ${AUTH[@]+"${AUTH[@]}"} >"$TMP/$key.sse" &
  local sse_pid=$!
  sleep 0.3
  local t0 t1 res
  t0="$(date +%s)"; res="$(post "/checks/$check_id/messages" "$body")"; t1="$(date +%s)"
  wait "$sse_pid" || true
  echo "events: $(tr -d '\r' <"$TMP/$key.sse" | grep -E '^event:' | awk '{print $2}' | paste -sd' ' -)"

  local verdict; verdict="$(jq -r .verdict <<<"$res")"
  echo "POST .../messages       -> $(jq -r '"\(.verdict) · \(.action) · \(.typology) (\(.confidence)) · needs_review \(.needs_review) · \(.latency_ms.total) ms"' <<<"$res") (wall $((t1 - t0)) s)"
  echo "  flags: $(jq -r '[.top_flags[].code] | join(", ")' <<<"$res")"
  echo "  [$(jq -r .customer_message.language <<<"$res")] $(jq -r .customer_message.headline <<<"$res")"
  echo "  $(jq -r .customer_message.body <<<"$res")"
  if [[ " $expected " == *" $verdict "* ]]; then echo "  ✔ expected $expected"
  else echo "  ✘ expected $expected, got $verdict"; FAILED=1; fi
  [[ "$key" == "tan" ]] && TAN_CASE="$(jq -r '.case_id // ""' <<<"$res")"
  return 0
}

for key in "${@:-tan raj aisyah}"; do for k in $key; do scenario "$k"; done; done

if [[ -n "$TAN_CASE" ]]; then
  bold "=== analyst: $TAN_CASE ==="
  for _ in $(seq 1 30); do  # the case file is written after the customer's answer
    title="$(get "/cases/$TAN_CASE" | jq -r '.case.case_file.title // empty')"
    [[ -n "$title" ]] && break; sleep 1
  done
  detail="$(get "/cases/$TAN_CASE")"
  echo "GET /cases/{id}         -> $(jq -r '"\(.case.verdict) · \(.case.status) · \(.case.case_file.title // "(case file pending)")"' <<<"$detail")"
  echo "  recommend: $(jq -r '.case.case_file.recommended_action // "-"' <<<"$detail") · evidence links: $(jq -r '.evidence_links | length' <<<"$detail") · watchlist matches: $(jq -r '.intel.watchlist_matches | length' <<<"$detail")"
  if [[ "$REPORT" == "1" ]]; then
    dec="$(post "/cases/$TAN_CASE/decision" '{"action":"REPORT_SCAM","note":"demo_curl.sh: confirmed MAS impersonation"}')"
    echo "POST .../decision       -> $(jq -r '"\(.status), \(.watchlist_added) entities added to the watchlist"' <<<"$dec")"
  fi
  echo "GET /cases?status=OPEN  -> $(get '/cases?status=OPEN' | jq -r 'length') open case(s)"
fi

if [[ "$RESET" == "1" ]]; then
  echo "POST /admin/reset-demo  -> $(post /admin/reset-demo '{}')"
fi
exit "$FAILED"
