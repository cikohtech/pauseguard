#!/usr/bin/env bash
# One-time Google Cloud infrastructure for PauseGuard (docs/DEPLOYMENT.md §1).
# Idempotent: every step looks for its resource first, so it is safe to re-run.
#
#   infra/setup.sh                       # project from GOOGLE_CLOUD_PROJECT in .env (or gcloud config)
#   PROJECT_ID=my-proj infra/setup.sh
#
# Creates (all data in asia-southeast1, Singapore): the APIs, Firestore (native), the BigQuery
# dataset, the evidence bucket (30-day lifecycle + CORS for signed PUTs from Hosting), the Artifact
# Registry repo, the admin-reset-token secret, and two service accounts with least privilege
# (SECURITY_PRIVACY.md §3):
#   pauseguard-api@    Cloud Run runtime identity
#   pauseguard-build@  builds the image for `gcloud run deploy --source` (roles/run.builder)
# Then: make seed-cloud, infra/set_analyst_claim.py, make deploy-api deploy-web smoke.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_value() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//; s/[[:space:]]*$//'; }

PROJECT_ID="${PROJECT_ID:-$(env_value GOOGLE_CLOUD_PROJECT)}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast1}"
DATASET="${BQ_DATASET:-pauseguard}"
BUCKET="${EVIDENCE_BUCKET:-$PROJECT_ID-pauseguard-evidence}"
REPO=pauseguard
SECRET=admin-reset-token
API_SA="pauseguard-api@$PROJECT_ID.iam.gserviceaccount.com"
BUILD_SA="pauseguard-build@$PROJECT_ID.iam.gserviceaccount.com"

[[ -n "$PROJECT_ID" && "$PROJECT_ID" != "your-project-id" ]] || {
  echo "Set GOOGLE_CLOUD_PROJECT in .env (or PROJECT_ID=...) first."; exit 1; }

step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
gc() { gcloud --project "$PROJECT_ID" --quiet "$@"; }
retry() {  # a new service account takes a few seconds to be usable in IAM policies
  local n
  for n in 1 2 3 4 5 6; do "$@" >/dev/null && return 0; echo "  (retrying in $((n * 5)) s)"; sleep $((n * 5)); done
  "$@" >/dev/null
}

echo "Project $PROJECT_ID · region $REGION · dataset $DATASET · bucket gs://$BUCKET"

step "APIs"
gc services enable run.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  logging.googleapis.com iamcredentials.googleapis.com firebasehosting.googleapis.com \
  firebaserules.googleapis.com identitytoolkit.googleapis.com
echo "  enabled"

step "Firestore (default) database, native mode"
if location="$(gc firestore databases describe --database='(default)' --format='value(locationId)' 2>/dev/null)"; then
  echo "  exists in $location"
  [[ "$location" == "$REGION" ]] || echo "  ⚠ expected $REGION; the location can't be changed"
else
  gc firestore databases create --location="$REGION" --type=firestore-native
fi

step "BigQuery dataset $DATASET"
if bq --project_id="$PROJECT_ID" show --dataset "$PROJECT_ID:$DATASET" >/dev/null 2>&1; then
  echo "  exists"
else
  bq --project_id="$PROJECT_ID" --location="$REGION" mk --dataset \
    --description "PauseGuard synthetic bank data + check analytics" "$PROJECT_ID:$DATASET"
fi

step "Evidence bucket gs://$BUCKET"
if gc storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  echo "  exists"
else
  gc storage buckets create "gs://$BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
CORS="$(mktemp)"; trap 'rm -f "$CORS"' EXIT
sed "s/pauseguard-sg/$PROJECT_ID/g" "$ROOT/infra/cors.json" >"$CORS"  # the Hosting origins
gc storage buckets update "gs://$BUCKET" --lifecycle-file="$ROOT/infra/lifecycle.json" --cors-file="$CORS" >/dev/null
echo "  lifecycle (delete after 30 days) + CORS set"

step "Artifact Registry repo $REPO"
if gc artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1; then
  echo "  exists"
else
  gc artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" \
    --description="PauseGuard API images"
fi

step "Secret $SECRET"
if gc secrets describe "$SECRET" >/dev/null 2>&1; then
  echo "  exists (value unchanged)"
else
  printf "%s" "$(openssl rand -hex 24)" | gc secrets create "$SECRET" --data-file=- \
    --replication-policy=user-managed --locations="$REGION"
fi

step "Service accounts"
for sa in pauseguard-api pauseguard-build; do
  if gc iam service-accounts describe "$sa@$PROJECT_ID.iam.gserviceaccount.com" >/dev/null 2>&1; then
    echo "  $sa exists"
  else
    gc iam service-accounts create "$sa" --display-name="PauseGuard ${sa#pauseguard-}"
  fi
done

step "IAM: $API_SA (least privilege)"
for role in aiplatform.user bigquery.jobUser datastore.user logging.logWriter cloudtrace.agent; do
  retry gc projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$API_SA" \
    --role="roles/$role" --condition=None
  echo "  project: roles/$role"
done
# Dataset-level IAM via `bq add-iam-policy-binding -d` needs allowlisting, so use the dataset's
# access list: WRITER is roles/bigquery.dataEditor on this dataset only.
DS_JSON="$(mktemp)"; trap 'rm -f "$CORS" "$DS_JSON"' EXIT
bq --project_id="$PROJECT_ID" --format=prettyjson show --dataset "$PROJECT_ID:$DATASET" >"$DS_JSON"
if jq -e --arg sa "$API_SA" 'any(.access[]; .userByEmail == $sa and .role == "WRITER")' "$DS_JSON" >/dev/null; then
  echo "  dataset $DATASET: WRITER (roles/bigquery.dataEditor) already granted"
else
  jq --arg sa "$API_SA" '.access += [{role: "WRITER", userByEmail: $sa}]' "$DS_JSON" >"$DS_JSON.new"
  retry bq --project_id="$PROJECT_ID" update --source "$DS_JSON.new" "$PROJECT_ID:$DATASET"
  rm -f "$DS_JSON.new"
  echo "  dataset $DATASET: WRITER (roles/bigquery.dataEditor)"
fi
retry gc storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$API_SA" \
  --role=roles/storage.objectAdmin
echo "  bucket: roles/storage.objectAdmin"
retry gc secrets add-iam-policy-binding "$SECRET" --member="serviceAccount:$API_SA" \
  --role=roles/secretmanager.secretAccessor
echo "  secret $SECRET: roles/secretmanager.secretAccessor"
# Cloud Run credentials have no private key: V4 signed URLs go through IAM signBlob, on itself only.
retry gc iam service-accounts add-iam-policy-binding "$API_SA" --member="serviceAccount:$API_SA" \
  --role=roles/iam.serviceAccountTokenCreator
echo "  itself: roles/iam.serviceAccountTokenCreator"

step "IAM: $BUILD_SA"
retry gc projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$BUILD_SA" \
  --role=roles/run.builder --condition=None
echo "  project: roles/run.builder"

printf '\n\033[1m✔ Infrastructure ready.\033[0m Next: make seed-cloud, uv --directory backend run python ../infra/set_analyst_claim.py, make deploy-api deploy-web smoke\n'
