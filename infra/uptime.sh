#!/usr/bin/env bash
# Evaluation-period safeguards for the live demo (docs/DEPLOYMENT.md §7), after `make deploy-api`.
# Idempotent: every step looks for its resource first, so it is safe to re-run.
#
#   ALERT_EMAIL=you@example.com infra/uptime.sh        # make uptime ALERT_EMAIL=...
#   RUN_JOBS=1 ...                                      # also run both Scheduler jobs once now
#
# Creates (flags checked against gcloud 588, 16 Oct 2026):
#   - an email notification channel for ALERT_EMAIL (REST: the GA gcloud has no `channels`)
#   - uptime checks every 5 min from all 6 regions on https://$PROJECT.web.app/ and the API's
#     /health (which answers 503 when Firestore, BigQuery or Gemini is down; Cloud Run reserves
#     /healthz)
#   - alert policies: an uptime check failing from 2+ regions; `selftest_failed` in the API logs or
#     a failed Scheduler attempt (infra/monitoring/*.json)
#   - Cloud Scheduler jobs (asia-southeast1, Asia/Singapore time) that send the X-Admin-Token:
#       pauseguard-reset-demo   every 6 hours   POST /api/v1/admin/reset-demo
#       pauseguard-selftest     daily 07:30     POST /api/v1/admin/selftest
# Costs: uptime checks and the channel are free at this volume; Scheduler is US$0.10/job/month
# after the billing account's 3 free jobs; alerting is billed per condition (cents).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_value() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//; s/[[:space:]]*$//'; }

PROJECT_ID="${PROJECT_ID:-$(env_value GOOGLE_CLOUD_PROJECT)}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-pauseguard-api}"
SECRET=admin-reset-token
TZ_NAME=Asia/Singapore
ALERT_EMAIL="${ALERT_EMAIL:-}"

[[ -n "$PROJECT_ID" && "$PROJECT_ID" != "your-project-id" ]] || {
  echo "Set GOOGLE_CLOUD_PROJECT in .env (or PROJECT_ID=...) first."; exit 1; }
[[ -n "$ALERT_EMAIL" ]] || { echo "Set ALERT_EMAIL=... (who gets the alerts)."; exit 1; }

step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
gc() { gcloud --project "$PROJECT_ID" --quiet "$@"; }
monitoring_api() {  # METHOD PATH [JSON]
  curl -sS --fail-with-body -X "$1" "https://monitoring.googleapis.com/v3/projects/$PROJECT_ID/$2" \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "x-goog-user-project: $PROJECT_ID" -H "Content-Type: application/json" ${3:+--data "$3"}
}

API_URL="$(gc run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
[[ -n "$API_URL" ]] || { echo "No Cloud Run service $SERVICE: make deploy-api first."; exit 1; }
API_HOST="${API_URL#https://}"
WEB_HOST="$PROJECT_ID.web.app"
echo "Project $PROJECT_ID · API $API_URL · web https://$WEB_HOST · alerts to $ALERT_EMAIL"

step "APIs"
gc services enable monitoring.googleapis.com cloudscheduler.googleapis.com
echo "  enabled"

step "Notification channel (email)"
CHANNEL="$(monitoring_api GET notificationChannels | jq -r --arg e "$ALERT_EMAIL" \
  '.notificationChannels[]? | select(.type == "email" and .labels.email_address == $e) | .name' | head -1)"
if [[ -n "$CHANNEL" ]]; then
  echo "  exists: $CHANNEL"
else
  body="$(jq -n --arg e "$ALERT_EMAIL" \
    '{type: "email", displayName: "PauseGuard alerts", labels: {email_address: $e}}')"
  CHANNEL="$(monitoring_api POST notificationChannels "$body" | jq -r .name)"
  echo "  created: $CHANNEL"
fi

step "Uptime checks (every 5 min, all regions)"
uptime_check() {  # NAME HOST PATH [extra flags...]
  local name="$1" host="$2" path="$3"; shift 3
  if [[ -n "$(gc monitoring uptime list-configs --filter="displayName=\"$name\"" --format='value(name)')" ]]; then
    echo "  $name exists"
  else
    gc monitoring uptime create "$name" --resource-type=uptime-url \
      --resource-labels="host=$host,project_id=$PROJECT_ID" --protocol=https --path="$path" \
      --validate-ssl=true --period=5 --timeout=20 "$@" >/dev/null
    echo "  $name created: https://$host$path"
  fi
}
uptime_check pauseguard-web "$WEB_HOST" / --matcher-content=PauseGuard --matcher-type=contains-string
uptime_check pauseguard-api-health "$API_HOST" /health

step "Alert policies"
policy() {  # FILE
  local file="$ROOT/infra/monitoring/$1" name tmp
  name="$(jq -r .displayName "$file")"
  if [[ -n "$(gc monitoring policies list --filter="displayName=\"$name\"" --format='value(name)')" ]]; then
    echo "  \"$name\" exists"
  else
    tmp="$(mktemp)"
    sed -e "s|__CHANNEL__|$CHANNEL|g" -e "s|__SERVICE__|$SERVICE|g" "$file" >"$tmp"
    gc monitoring policies create --policy-from-file="$tmp" >/dev/null
    rm -f "$tmp"
    echo "  \"$name\" created"
  fi
}
policy uptime-policy.json
policy selftest-policy.json

step "Cloud Scheduler jobs ($REGION, $TZ_NAME)"
TOKEN="$(gc secrets versions access latest --secret "$SECRET")"
job() {  # NAME SCHEDULE PATH DEADLINE DESCRIPTION
  local name="$1" schedule="$2" uri="$API_URL$3" deadline="$4" desc="$5"
  if gc scheduler jobs describe "$name" --location "$REGION" >/dev/null 2>&1; then
    # Refreshes the URI, schedule and token (after a token rotation, re-run this script).
    gc scheduler jobs update http "$name" --location "$REGION" --schedule "$schedule" \
      --time-zone "$TZ_NAME" --uri "$uri" --http-method post --attempt-deadline "$deadline" \
      --update-headers "X-Admin-Token=$TOKEN" --description "$desc" >/dev/null
    echo "  $name updated: $schedule → POST $3"
  else
    gc scheduler jobs create http "$name" --location "$REGION" --schedule "$schedule" \
      --time-zone "$TZ_NAME" --uri "$uri" --http-method post --attempt-deadline "$deadline" \
      --headers "X-Admin-Token=$TOKEN" --max-retry-attempts 0 --description "$desc" >/dev/null
    echo "  $name created: $schedule → POST $3"
  fi
}
job pauseguard-reset-demo "0 */6 * * *" /api/v1/admin/reset-demo 60s \
  "Every 6 h: clear the demo personas' checks and cases, restore the seed watchlist (DEPLOYMENT §7.4)"
job pauseguard-selftest "30 7 * * *" /api/v1/admin/selftest 120s \
  "Daily: Aisyah's GREEN scenario end to end through Gemini; 503 + alert on failure (DEPLOYMENT §7.3)"

if [[ "${RUN_JOBS:-0}" == 1 ]]; then
  step "Running both jobs once"
  for name in pauseguard-reset-demo pauseguard-selftest; do
    gc scheduler jobs run "$name" --location "$REGION" >/dev/null && echo "  $name triggered"
  done
  echo "  results: gcloud scheduler jobs describe <job> --location $REGION --format='value(status,lastAttemptTime)'"
fi

printf '\n\033[1m✓ Safeguards in place.\033[0m Uptime: https://console.cloud.google.com/monitoring/uptime?project=%s\n' "$PROJECT_ID"
