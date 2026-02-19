###############################################################################
# Variables
###############################################################################

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "agentcore-demo"
}

variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "devops-copilot"
}

variable "agent_image_tag" {
  description = "Docker image tag for the agent container"
  type        = string
  default     = "latest"
}

variable "okta_org_name" {
  description = "Okta org name (e.g. dev-12345678)"
  type        = string
}

variable "okta_base_url" {
  description = "Okta base URL"
  type        = string
  default     = "okta.com"
}

variable "okta_api_token" {
  description = "Okta API token for provisioning"
  type        = string
  sensitive   = true
}

variable "agentgateway_llm_endpoint" {
  description = "Public HTTPS endpoint for AgentGateway LLM proxy (e.g. ngrok URL)"
  type        = string
  default     = "https://llm-agentgateway.ngrok.app"
}

variable "agentgateway_mcp_endpoint" {
  description = "Public HTTPS endpoint for AgentGateway MCP gateway (e.g. ngrok URL)"
  type        = string
  default     = "https://mcp-agentgateway.ngrok.app"
}

variable "agent_redirect_uri" {
  description = "OAuth2 redirect URI for the user-facing app"
  type        = string
  default     = "http://localhost:8080/callback"
}

variable "agent_post_logout_uri" {
  description = "Post-logout redirect URI"
  type        = string
  default     = "http://localhost:8080"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "agentcore-demo"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}
