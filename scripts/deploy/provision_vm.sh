#!/usr/bin/env bash
# provision_vm.sh — create the GCP VM that co-hosts the trading bot + Command Center.
#
# RUN THIS ON YOUR MACHINE (where gcloud is authenticated), NOT on the VM.
# It is read-only on trading surfaces — it only creates cloud infra. Re-running is
# mostly safe: API enables are idempotent; VM creation errors if the VM already exists.
#
# Prereqs: gcloud CLI installed + `gcloud auth login`, billing/trial linked to the project.
#
# Override any of these via env, e.g.:  PROJECT=my-proj ZONE=us-east1-b ./provision_vm.sh
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT=<your-gcp-project-id>}"
ZONE="${ZONE:-us-central1-a}"
REGION="${REGION:-${ZONE%-*}}"
MACHINE="${MACHINE:-e2-medium}"
VM="${VM:-trading-stack}"
DISK_GB="${DISK_GB:-30}"
IMAGE_FAMILY="${IMAGE_FAMILY:-ubuntu-2204-lts}"
IMAGE_PROJECT="${IMAGE_PROJECT:-ubuntu-os-cloud}"

echo ">> Project:  $PROJECT"
echo ">> Zone:     $ZONE  (region $REGION)"
echo ">> Machine:  $MACHINE   VM: $VM   Disk: ${DISK_GB}GB"

gcloud config set project "$PROJECT"

echo ">> Enabling required APIs (compute, vertex/aiplatform)..."
gcloud services enable compute.googleapis.com aiplatform.googleapis.com

echo ">> Creating VM (Ubuntu 22.04, no public app ports)..."
gcloud compute instances create "$VM" \
  --zone="$ZONE" \
  --machine-type="$MACHINE" \
  --image-family="$IMAGE_FAMILY" \
  --image-project="$IMAGE_PROJECT" \
  --boot-disk-size="${DISK_GB}GB" \
  --boot-disk-type=pd-balanced \
  --no-service-account --no-scopes 2>/dev/null \
  || gcloud compute instances create "$VM" \
       --zone="$ZONE" \
       --machine-type="$MACHINE" \
       --image-family="$IMAGE_FAMILY" \
       --image-project="$IMAGE_PROJECT" \
       --boot-disk-size="${DISK_GB}GB" \
       --boot-disk-type=pd-balanced

# NOTE: we deliberately add NO ingress firewall rules beyond GCP's default SSH (tcp:22).
# Dashboards are reached via SSH tunnel only — never expose 8001/8765/3000 publicly.

cat <<EOF

>> VM created.

NEXT:
  1. SSH in:        gcloud compute ssh $VM --zone=$ZONE
  2. Copy setup:    gcloud compute scp scripts/deploy/setup_vm.sh $VM:~ --zone=$ZONE
  3. On the VM:     bash ~/setup_vm.sh
  4. Service acct + Vertex key, .env files, then enable services — see docs/DEPLOYMENT.md

  Budget alert (recommended — protects the \$300 trial). Example:
    # gcloud billing budgets create --billing-account=<BILLING_ACCT_ID> \\
    #   --display-name="trading-stack \$50" --budget-amount=50USD \\
    #   --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
  (Full command + email wiring in docs/DEPLOYMENT.md.)

  REMINDER: the \$300 free trial expires 2026-08-27, then converts to paid on consent.
EOF
