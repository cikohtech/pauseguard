#!/usr/bin/env bash
# Smoke test of the deployed stack (DEPLOYMENT.md §4), run by `make smoke`:
#   1. GET /health on Cloud Run (Cloud Run reserves /healthz)
#   2. the Firebase Hosting page loads, and the API answers CORS preflights from that origin
#   3. Firebase Auth for real: an anonymous customer may start a check but not read cases; the
#      demo analyst (custom claim role=analyst) may read cases
#   4. the 3 demo scenarios end to end (scripts/demo_curl.sh, admin token), then /admin/reset-demo
#
# Env (all optional; defaults are looked up with gcloud):
#   BASE        the API URL                 WEB  the Hosting URL (https://<project>.web.app)
#   ADMIN_TOKEN Secret Manager admin-reset-token
#   FIREBASE_API_KEY  the web app's API key (default: from web/.env.production.local)
#   ANALYST_EMAIL / ANALYST_PASSWORD  the public demo login (infra/set_analyst_claim.py)
#   SCENARIOS   e.g. "tan" (default: all three); AUTH=0 skips step 3
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${PROJECT:-$(grep -E '^GOOGLE_CLOUD_PROJECT=' "$ROOT/.env" | cut -d= -f2 | awk '{print $1}')}"
REGION="${REGION:-asia-southeast1}"
BASE="${BASE:-$(gcloud run services describe pauseguard-api --project "$PROJECT" --region "$REGION" --format='value(status.url)')}"
WEB="${WEB:-https://$PROJECT.web.app}"
ADMIN_TOKEN="${ADMIN_TOKEN:-$(gcloud secrets versions access latest --secret admin-reset-token --project "$PROJECT")}"
ANALYST_EMAIL="${ANALYST_EMAIL:-analyst@harbourbank.example}"
ANALYST_PASSWORD="${ANALYST_PASSWORD:-HarbourDemo2026}"
API="$BASE/api/v1"
command -v jq >/dev/null || { echo "jq is required (brew install jq)"; exit 2; }

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  ✔ %s\n' "$*"; }
fail() { printf '  ✘ %s\n' "$*"; exit 1; }
status_of() { curl -sS -o /dev/null -w '%{http_code}' "$@"; }

bold "API $BASE · web $WEB"
health="$(curl -sS --fail-with-body "$BASE/health")" || fail "/health: $health"
ok "/health $(jq -c . <<<"$health")"

page="$(curl -sS --fail-with-body "$WEB/")" || fail "Hosting: $WEB"
grep -qi '<div id="root">' <<<"$page" && ok "Hosting serves the app at $WEB" || fail "Hosting: no app root"
code="$(status_of "$WEB/app/does-not-exist")"
[[ "$code" == 200 ]] && ok "SPA rewrite: deep links return 200" || fail "SPA rewrite: $code"
allow="$(curl -sS -o /dev/null -D - -X OPTIONS "$API/checks" -H "Origin: $WEB" \
  -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: authorization,content-type' \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')"
[[ "$allow" == "$WEB" ]] && ok "CORS preflight from $WEB allowed" || fail "CORS: allow-origin '$allow'"

if [[ "${AUTH:-1}" == "1" ]]; then
  bold "Firebase Auth (live tokens)"
  KEY="${FIREBASE_API_KEY:-$(sed -n 's/^VITE_FIREBASE_CONFIG_JSON=//p' "$ROOT/web/.env.production.local" 2>/dev/null | jq -r '.apiKey // empty')}"
  [[ -n "$KEY" ]] || fail "no FIREBASE_API_KEY (web/.env.production.local)"
  IDT="https://identitytoolkit.googleapis.com/v1/accounts"
  anon="$(curl -sS -X POST "$IDT:signUp?key=$KEY" -H 'Content-Type: application/json' \
    -d '{"returnSecureToken":true}' | jq -r '.idToken // empty')"
  [[ -n "$anon" ]] || fail "anonymous sign-in failed (is the Anonymous provider enabled?)"
  ok "anonymous sign-in"
  started="$(curl -sS --fail-with-body -X POST "$API/checks" -H "Authorization: Bearer $anon" \
    -H 'Content-Type: application/json' \
    -d '{"customer_id":"cust_003","language":"en","transfer":{"payee_name":"Wong Kah Wai","account_number":"436-905127-318","bank_name":"Kampong Federal Bank","dest_type":"LOCAL_BANK","amount":3200,"currency":"SGD"}}')" \
    || fail "POST /checks as an anonymous customer: $started"
  ok "anonymous customer: POST /checks -> $(jq -r '"\(.check_id) \(.status)"' <<<"$started")"
  code="$(status_of "$API/cases?status=OPEN" -H "Authorization: Bearer $anon")"
  [[ "$code" == 403 ]] && ok "anonymous customer: GET /cases -> 403" || fail "anonymous GET /cases -> $code (want 403)"
  analyst="$(curl -sS -X POST "$IDT:signInWithPassword?key=$KEY" -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg e "$ANALYST_EMAIL" --arg p "$ANALYST_PASSWORD" '{email:$e, password:$p, returnSecureToken:true}')" \
    | jq -r '.idToken // empty')"
  [[ -n "$analyst" ]] || fail "analyst sign-in failed ($ANALYST_EMAIL; run make analyst)"
  code="$(status_of "$API/cases?status=OPEN" -H "Authorization: Bearer $analyst")"
  [[ "$code" == 200 ]] && ok "analyst $ANALYST_EMAIL: GET /cases -> 200" || fail "analyst GET /cases -> $code (want 200)"
fi

bold "Demo scenarios"
BASE="$BASE" ADMIN_TOKEN="$ADMIN_TOKEN" RESET=1 "$ROOT/scripts/demo_curl.sh" ${SCENARIOS:-}
