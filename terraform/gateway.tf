###############################################################################
# AgentCore Gateway (via AWS CLI — no native TF resource yet)
###############################################################################

resource "null_resource" "gateway" {
  triggers = {
    name        = "${local.name_prefix}-gateway"
    role_arn    = aws_iam_role.agentcore_gateway.arn
    aws_profile = var.aws_profile
    aws_region  = var.aws_region
    okta_issuer = "https://${var.okta_org_name}.${var.okta_base_url}/oauth2/${data.okta_auth_server.default.id}"
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      # Check if gateway already exists
      EXISTING=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control list-gateways \
        --no-cli-pager --output json 2>/dev/null | \
        jq -r '.items[]? | select(.name == "${self.triggers.name}") | .gatewayId' || true)

      if [ -n "$EXISTING" ]; then
        echo "Gateway already exists: $EXISTING"
        echo "$EXISTING" > ${path.module}/gateway_id.txt
        exit 0
      fi

      RESULT=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control create-gateway \
        --name "${self.triggers.name}" \
        --role-arn "${self.triggers.role_arn}" \
        --protocol-type "MCP" \
        --authorizer-type "CUSTOM_JWT" \
        --authorizer-configuration "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"${self.triggers.okta_issuer}/.well-known/openid-configuration\",\"allowedAudience\":[\"api://default\"]}}" \
        --description "Gateway to AgentGateway on k8s-rooster (Okta JWT auth)" \
        --no-cli-pager --output json)

      echo "$RESULT" | jq -r '.gatewayId' > ${path.module}/gateway_id.txt
      echo "Created gateway: $(cat ${path.module}/gateway_id.txt)"

      # Wait for gateway to be ready
      GATEWAY_ID=$(cat ${path.module}/gateway_id.txt)
      for i in $(seq 1 30); do
        STATUS=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control get-gateway \
          --gateway-identifier "$GATEWAY_ID" \
          --no-cli-pager --output json | jq -r '.status')
        echo "Gateway status: $STATUS (attempt $i/30)"
        if [ "$STATUS" = "READY" ] || [ "$STATUS" = "ACTIVE" ]; then break; fi
        if [ "$STATUS" = "CREATE_FAILED" ]; then echo "FAILED"; exit 1; fi
        sleep 10
      done
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      set -e
      if [ -f ${path.module}/gateway_id.txt ]; then
        GATEWAY_ID=$(cat ${path.module}/gateway_id.txt)
        echo "Deleting gateway: $GATEWAY_ID"
        aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control delete-gateway \
          --gateway-identifier "$GATEWAY_ID" \
          --no-cli-pager 2>/dev/null || true
        rm -f ${path.module}/gateway_id.txt
      fi
    EOT
  }

  depends_on = [aws_iam_role_policy.agentcore_gateway]
}

###############################################################################
# Gateway Target — MCP Server (AgentGateway on k8s-rooster)
###############################################################################

resource "null_resource" "gateway_target_mcp" {
  triggers = {
    name             = "agentgateway-mcp"
    gateway_endpoint = var.agentgateway_endpoint
    aws_profile      = var.aws_profile
    aws_region       = var.aws_region
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      GATEWAY_ID=$(cat ${path.module}/gateway_id.txt)

      # Check if target already exists
      EXISTING=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control list-gateway-targets \
        --gateway-identifier "$GATEWAY_ID" \
        --no-cli-pager --output json 2>/dev/null | \
        jq -r '.items[]? | select(.name == "${self.triggers.name}") | .targetId' || true)

      if [ -n "$EXISTING" ]; then
        echo "Gateway target already exists: $EXISTING"
        echo "$EXISTING" > ${path.module}/gateway_target_id.txt
        exit 0
      fi

      RESULT=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control create-gateway-target \
        --gateway-identifier "$GATEWAY_ID" \
        --name "${self.triggers.name}" \
        --description "AgentGateway MCP server on k8s-rooster" \
        --target-configuration '{"mcp":{"mcpServer":{"endpoint":"${self.triggers.gateway_endpoint}"}}}' \
        --no-cli-pager --output json)

      echo "$RESULT" | jq -r '.targetId' > ${path.module}/gateway_target_id.txt
      echo "Created gateway target: $(cat ${path.module}/gateway_target_id.txt)"
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      set -e
      if [ -f ${path.module}/gateway_id.txt ] && [ -f ${path.module}/gateway_target_id.txt ]; then
        GATEWAY_ID=$(cat ${path.module}/gateway_id.txt)
        TARGET_ID=$(cat ${path.module}/gateway_target_id.txt)
        echo "Deleting gateway target: $TARGET_ID"
        aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control delete-gateway-target \
          --gateway-identifier "$GATEWAY_ID" \
          --target-id "$TARGET_ID" \
          --no-cli-pager 2>/dev/null || true
        rm -f ${path.module}/gateway_target_id.txt
      fi
    EOT
  }

  depends_on = [null_resource.gateway]
}
