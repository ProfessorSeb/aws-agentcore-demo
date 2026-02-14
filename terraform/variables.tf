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

variable "agentgateway_endpoint" {
  description = "Public HTTPS endpoint for AgentGateway on k8s-rooster (e.g. ngrok URL)"
  type        = string
  default     = "https://agentgateway.example.com"
}

variable "okta_discovery_url" {
  description = "Okta OIDC discovery URL (for future OAuth2 integration)"
  type        = string
  default     = "https://your-org.okta.com/.well-known/openid-configuration"
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
