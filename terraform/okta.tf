###############################################################################
# Okta Provider & App Registrations
# Provides OAuth2 identity for agent → AgentGateway MCP authentication:
#   User → (IAM) → AgentCore Runtime → Agent → (Okta JWT) → AgentGateway → MCP
###############################################################################

provider "okta" {
  org_name  = var.okta_org_name
  base_url  = var.okta_base_url
  api_token = var.okta_api_token
}

###############################################################################
# Auth Server — use "default" or create a custom one
###############################################################################

data "okta_auth_server" "default" {
  name = "default"
}

###############################################################################
# Custom Scopes — MCP tool access (validated by AgentGateway)
###############################################################################

resource "okta_auth_server_scope" "mcp_read" {
  auth_server_id   = data.okta_auth_server.default.id
  name             = "mcp:read"
  description      = "Read access to MCP tools via AgentGateway"
  consent          = "IMPLICIT"
  metadata_publish = "ALL_CLIENTS"
}

resource "okta_auth_server_scope" "mcp_write" {
  auth_server_id   = data.okta_auth_server.default.id
  name             = "mcp:write"
  description      = "Write access to MCP tools via AgentGateway"
  consent          = "IMPLICIT"
  metadata_publish = "ALL_CLIENTS"
}

resource "okta_auth_server_scope" "mcp_admin" {
  auth_server_id   = data.okta_auth_server.default.id
  name             = "mcp:admin"
  description      = "Admin access to MCP tools (e.g. Slack post, GitHub write)"
  consent          = "REQUIRED"
  metadata_publish = "ALL_CLIENTS"
}

###############################################################################
# App 1 — User-Facing Client (Authorization Code + PKCE)
# For future user-facing UIs that need human identity
###############################################################################

resource "okta_app_oauth" "agentcore_client" {
  label                      = "${var.project_name}-client"
  type                       = "web"
  grant_types                = ["authorization_code", "refresh_token"]
  redirect_uris              = [var.agent_redirect_uri]
  post_logout_redirect_uris  = [var.agent_post_logout_uri]
  token_endpoint_auth_method = "client_secret_basic"
  response_types             = ["code"]
}

###############################################################################
# App 2 — Agent Service (Machine-to-Machine)
# The agent uses client_credentials to get a JWT for AgentGateway MCP calls
###############################################################################

resource "okta_app_oauth" "agentcore_service" {
  label                      = "${var.project_name}-service"
  type                       = "service"
  grant_types                = ["client_credentials"]
  token_endpoint_auth_method = "client_secret_basic"
  response_types             = ["token"]
}

###############################################################################
# Auth Server Policy + Rule — Allow both apps to request MCP scopes
###############################################################################

resource "okta_auth_server_policy" "agentcore" {
  auth_server_id   = data.okta_auth_server.default.id
  name             = "AgentCore Policy"
  description      = "Token policy for AgentCore demo apps"
  priority         = 1
  client_whitelist = [
    okta_app_oauth.agentcore_client.client_id,
    okta_app_oauth.agentcore_service.client_id,
  ]
}

data "okta_group" "everyone" {
  name = "Everyone"
}

resource "okta_auth_server_policy_rule" "agentcore_rule" {
  auth_server_id                = data.okta_auth_server.default.id
  policy_id                     = okta_auth_server_policy.agentcore.id
  name                          = "Allow MCP scopes"
  priority                      = 1
  grant_type_whitelist          = ["authorization_code", "client_credentials"]
  scope_whitelist               = ["openid", "profile", "email", "mcp:read", "mcp:write", "mcp:admin"]
  group_whitelist               = [data.okta_group.everyone.id]
  access_token_lifetime_minutes   = 60
  refresh_token_lifetime_minutes  = 1440
  refresh_token_window_minutes    = 1440
  inline_hook_id                  = ""
}

###############################################################################
# Outputs
###############################################################################

output "okta_issuer" {
  description = "Okta OIDC issuer URL"
  value       = "https://${var.okta_org_name}.${var.okta_base_url}/oauth2/${data.okta_auth_server.default.id}"
}

output "okta_jwks_uri" {
  description = "JWKS URI for token validation (use in AgentGateway)"
  value       = "https://${var.okta_org_name}.${var.okta_base_url}/oauth2/${data.okta_auth_server.default.id}/v1/keys"
}

output "okta_token_url" {
  description = "Token endpoint for client_credentials grant"
  value       = "https://${var.okta_org_name}.${var.okta_base_url}/oauth2/${data.okta_auth_server.default.id}/v1/token"
}

output "okta_client_id" {
  description = "User-facing app client ID"
  value       = okta_app_oauth.agentcore_client.client_id
}

output "okta_client_secret" {
  description = "User-facing app client secret"
  value       = okta_app_oauth.agentcore_client.client_secret
  sensitive   = true
}

output "okta_service_client_id" {
  description = "Agent service client ID (set as OKTA_CLIENT_ID in agent env)"
  value       = okta_app_oauth.agentcore_service.client_id
}

output "okta_service_client_secret" {
  description = "Agent service client secret (set as OKTA_CLIENT_SECRET in agent env)"
  value       = okta_app_oauth.agentcore_service.client_secret
  sensitive   = true
}
