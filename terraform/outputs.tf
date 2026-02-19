###############################################################################
# Outputs
###############################################################################

output "ecr_repository_url" {
  description = "ECR repository URL for the agent container"
  value       = aws_ecr_repository.agent.repository_url
}

output "agentcore_runtime_role_arn" {
  description = "IAM role ARN for the AgentCore runtime"
  value       = aws_iam_role.agentcore_runtime.arn
}

# Note: Runtime ID, Endpoint ID, and Gateway ID are stored in local files
# (runtime_id.txt, endpoint_id.txt, gateway_id.txt) by the null_resource provisioners.
# Read them with: cat terraform/runtime_id.txt
