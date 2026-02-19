#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TF_DIR="$PROJECT_DIR/terraform"
AGENT_DIR="$PROJECT_DIR/agent"

AWS_PROFILE="${AWS_PROFILE:-agentcore-demo}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=== AWS AgentCore Demo — Deploy ==="
echo "Profile: $AWS_PROFILE | Region: $AWS_REGION"

# Verify AWS credentials
echo ""
echo "--- Verifying AWS credentials ---"
ACCOUNT_ID=$(aws --profile "$AWS_PROFILE" sts get-caller-identity --query Account --output text)
echo "Account: $ACCOUNT_ID"

# Step 1: Terraform init + apply (creates ECR, IAM, etc.)
echo ""
echo "--- Step 1: Terraform Init ---"
cd "$TF_DIR"
terraform init -upgrade

echo ""
echo "--- Step 2: Terraform Apply (IAM + ECR only first) ---"
terraform apply -target=aws_ecr_repository.agent -target=aws_iam_role.agentcore_runtime -auto-approve

# Step 2: Build and push agent container
ECR_URI=$(terraform output -raw ecr_repository_url)
echo ""
echo "--- Step 3: Build & Push Agent Container ---"
echo "ECR: $ECR_URI"

aws --profile "$AWS_PROFILE" ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

cd "$AGENT_DIR"
docker build --platform linux/amd64 -t "$ECR_URI:latest" .
docker push "$ECR_URI:latest"
echo "Agent image pushed successfully."

# Step 3: Apply remaining Terraform (AgentCore resources)
echo ""
echo "--- Step 4: Terraform Apply (all resources) ---"
cd "$TF_DIR"
terraform apply -auto-approve

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Resource IDs:"
[ -f runtime_id.txt ] && echo "  Runtime:  $(cat runtime_id.txt)"
[ -f endpoint_id.txt ] && echo "  Endpoint: $(cat endpoint_id.txt)"
echo ""
echo "ECR: $ECR_URI"
