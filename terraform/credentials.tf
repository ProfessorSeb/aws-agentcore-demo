###############################################################################
# Credential Provider — Okta OAuth2 (On-Behalf-Of)
# Wires Okta into AgentCore Gateway for delegated identity to MCP tools
###############################################################################

resource "null_resource" "okta_credential_provider" {
  triggers = {
    name         = "${local.name_prefix}-okta-obo"
    aws_profile  = var.aws_profile
    aws_region   = var.aws_region
    issuer       = "https://${var.okta_org_name}.${var.okta_base_url}/oauth2/${data.okta_auth_server.default.id}"
    client_id    = okta_app_oauth.agentcore_service.client_id
    client_secret = okta_app_oauth.agentcore_service.client_secret
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      GATEWAY_ID=$(cat ${path.module}/gateway_id.txt)

      # Create OAuth2 credential provider for OBO flow
      aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control create-oauth2-credential-provider \
        --name "${self.triggers.name}" \
        --credential-provider-vendor "CustomOIDC" \
        --oauth2-provider-config-properties '{
          "issuer": "${self.triggers.issuer}",
          "clientId": "${self.triggers.client_id}",
          "clientSecret": "${self.triggers.client_secret}",
          "authorizationEndpoint": "${self.triggers.issuer}/v1/authorize",
          "tokenEndpoint": "${self.triggers.issuer}/v1/token",
          "scopes": ["openid", "mcp:read", "mcp:write"]
        }' \
        --no-cli-pager --output json | tee ${path.module}/okta_credential_provider.json

      echo "Okta OAuth2 credential provider created"
    EOT
  }

  depends_on = [
    null_resource.gateway,
    okta_app_oauth.agentcore_service,
  ]
}

# NOTE: Gateway authorizer (CUSTOM_JWT with Okta) is set at creation time
# in gateway.tf — AWS does not allow changing authorizer type after creation.
