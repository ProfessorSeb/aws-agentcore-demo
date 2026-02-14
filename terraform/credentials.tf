###############################################################################
# Credential Providers — Placeholders for future Okta OBO integration
###############################################################################

# NOTE: OAuth2 credential provider will be created when Okta integration is ready.
# The commands would be:
#
#   aws --profile agentcore-demo bedrock-agentcore-control create-oauth2-credential-provider \
#     --name "okta-obo" \
#     --credential-provider-vendor "CustomOIDC" \
#     --oauth2-provider-config-properties '{...}' \
#
# For now, we just document the placeholder.

# --- API Key Credential Provider (example for future use) ---
# Uncomment when you have an API key to configure:
#
# resource "null_resource" "api_key_credential" {
#   triggers = {
#     name        = "${local.name_prefix}-api-key"
#     aws_profile = var.aws_profile
#     aws_region  = var.aws_region
#   }
#
#   provisioner "local-exec" {
#     command = <<-EOT
#       aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
#         bedrock-agentcore-control create-api-key-credential-provider \
#         --name "${self.triggers.name}" \
#         --api-key "<stored-in-secrets-manager>" \
#         --no-cli-pager --output json
#     EOT
#   }
# }
