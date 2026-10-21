#!/usr/bin/env bash
# Tear down what scripts/setup_gcp.sh created (as far as Google Cloud allows).
#
#   * Deletes the BigQuery dataset `chimera_telemetry` (and its tables).
#   * Schedules destruction of Cloud KMS key version 1 of `chimera-patch-signer`
#     (key rings and keys themselves cannot be deleted in Cloud KMS; destroyed versions stop billing).
#
# Usage:  scripts/teardown_gcp.sh [--yes]
set -euo pipefail

ASSUME_YES=false
[[ "${1:-}" == "--yes" || "${1:-}" == "-y" ]] && ASSUME_YES=true

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
DATASET="${CHRYSALIS_BQ_DATASET:-chimera_telemetry}"
KMS_LOCATION="${CHRYSALIS_KMS_LOCATION:-us-central1}"
KEY_RING="chimera-governance-ring"
KEY_NAME="chimera-patch-signer"

echo "Will delete BigQuery dataset ${PROJECT_ID}:${DATASET} and destroy KMS key version"
echo "projects/${PROJECT_ID}/locations/${KMS_LOCATION}/keyRings/${KEY_RING}/cryptoKeys/${KEY_NAME}/cryptoKeyVersions/1"
if [[ "${ASSUME_YES}" != true ]]; then
  read -r -p "Proceed? [y/N] " reply
  [[ "${reply}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

bq --project_id="${PROJECT_ID}" rm -r -f -d "${PROJECT_ID}:${DATASET}" || true
gcloud kms keys versions destroy 1 --key "${KEY_NAME}" --keyring "${KEY_RING}" \
  --location "${KMS_LOCATION}" --project "${PROJECT_ID}" --quiet || true
echo "Done."
