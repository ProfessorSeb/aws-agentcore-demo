#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(dirname "$SCRIPT_DIR")/terraform"

AWS_PROFILE="${AWS_PROFILE:-agentcore-demo}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=== AWS AgentCore Demo — Test ==="

# Check resource IDs
echo ""
echo "--- Resource Status ---"
for f in runtime_id endpoint_id gateway_id gateway_target_id; do
  FILE="$TF_DIR/${f}.txt"
  if [ -f "$FILE" ]; then
    echo "  $f: $(cat "$FILE")"
  else
    echo "  $f: NOT FOUND"
  fi
done

# Check runtime status
if [ -f "$TF_DIR/runtime_id.txt" ]; then
  RUNTIME_ID=$(cat "$TF_DIR/runtime_id.txt")
  echo ""
  echo "--- Runtime Status ---"
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$RUNTIME_ID" \
    --no-cli-pager --output json | jq '{status, agentRuntimeName, agentRuntimeId}'
fi

# Check endpoint status
if [ -f "$TF_DIR/endpoint_id.txt" ]; then
  ENDPOINT_ID=$(cat "$TF_DIR/endpoint_id.txt")
  echo ""
  echo "--- Endpoint Status ---"
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    bedrock-agentcore-control get-agent-runtime-endpoint \
    --agent-runtime-endpoint-id "$ENDPOINT_ID" \
    --no-cli-pager --output json | jq '{status, name, agentRuntimeEndpointId}'
fi

# Check gateway status
if [ -f "$TF_DIR/gateway_id.txt" ]; then
  GATEWAY_ID=$(cat "$TF_DIR/gateway_id.txt")
  echo ""
  echo "--- Gateway Status ---"
  aws --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    bedrock-agentcore-control get-gateway \
    --gateway-identifier "$GATEWAY_ID" \
    --no-cli-pager --output json | jq '{status, name, gatewayId}'
fi

echo ""
echo "--- Local Agent Test ---"
echo "To test locally: cd agent && python agent.py"
echo "Then: curl -X POST http://localhost:8080/invoke -H 'Content-Type: application/json' -d '{\"input\": \"status\"}'"
echo ""
echo "=== Test Complete ==="
