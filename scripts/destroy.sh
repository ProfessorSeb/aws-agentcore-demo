#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")/terraform"

AWS_PROFILE="${AWS_PROFILE:-agentcore-demo}"

echo "=== AWS AgentCore Demo — Destroy ==="
echo "Profile: $AWS_PROFILE"
echo ""
echo "⚠️  This will destroy ALL resources. Press Ctrl+C to abort."
read -p "Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

cd "$TF_DIR"
terraform destroy -auto-approve

echo ""
echo "=== Destroy Complete ==="
