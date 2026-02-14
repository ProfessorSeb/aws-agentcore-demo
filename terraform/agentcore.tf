###############################################################################
# ECR Repository
###############################################################################

resource "aws_ecr_repository" "agent" {
  name                 = "${local.name_prefix}-agent"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

###############################################################################
# AgentCore Runtime (via AWS CLI — no native TF resource yet)
###############################################################################

resource "null_resource" "agent_runtime" {
  triggers = {
    name        = "${local.name_prefix}_runtime"
    role_arn    = aws_iam_role.agentcore_runtime.arn
    image_uri   = "${local.ecr_uri}:${var.agent_image_tag}"
    aws_profile = var.aws_profile
    aws_region  = var.aws_region
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e

      # Check if runtime already exists
      EXISTING=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control list-agent-runtimes \
        --no-cli-pager --output json 2>/dev/null | \
        jq -r '.agentRuntimeSummaries[]? | select(.agentRuntimeName == "${self.triggers.name}") | .agentRuntimeId' || true)

      if [ -n "$EXISTING" ]; then
        echo "Runtime already exists: $EXISTING"
        echo "$EXISTING" > ${path.module}/runtime_id.txt
        exit 0
      fi

      RESULT=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control create-agent-runtime \
        --agent-runtime-name "${self.triggers.name}" \
        --role-arn "${self.triggers.role_arn}" \
        --agent-runtime-artifact '{"containerConfiguration":{"containerUri":"${self.triggers.image_uri}"}}' \
        --network-configuration '{"networkMode":"PUBLIC"}' \
        --description "DevOps Copilot agent runtime" \
        --no-cli-pager --output json)

      echo "$RESULT" | jq -r '.agentRuntimeId' > ${path.module}/runtime_id.txt
      echo "Created runtime: $(cat ${path.module}/runtime_id.txt)"

      # Wait for runtime to be ready
      RUNTIME_ID=$(cat ${path.module}/runtime_id.txt)
      for i in $(seq 1 30); do
        STATUS=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control get-agent-runtime \
          --agent-runtime-id "$RUNTIME_ID" \
          --no-cli-pager --output json | jq -r '.status')
        echo "Runtime status: $STATUS (attempt $i/30)"
        if [ "$STATUS" = "READY" ]; then break; fi
        if [ "$STATUS" = "CREATE_FAILED" ]; then echo "FAILED"; exit 1; fi
        sleep 10
      done
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      set -e
      if [ -f ${path.module}/runtime_id.txt ]; then
        RUNTIME_ID=$(cat ${path.module}/runtime_id.txt)
        echo "Deleting runtime: $RUNTIME_ID"
        aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control delete-agent-runtime \
          --agent-runtime-id "$RUNTIME_ID" \
          --no-cli-pager 2>/dev/null || true
        rm -f ${path.module}/runtime_id.txt
      fi
    EOT
  }

  depends_on = [aws_iam_role_policy.agentcore_runtime]
}

###############################################################################
# AgentCore Runtime Endpoint
###############################################################################

resource "null_resource" "agent_runtime_endpoint" {
  triggers = {
    name        = "${local.name_prefix}_endpoint"
    aws_profile = var.aws_profile
    aws_region  = var.aws_region
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      RUNTIME_ID=$(cat ${path.module}/runtime_id.txt)

      # Check if endpoint already exists
      EXISTING=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control list-agent-runtime-endpoints \
        --agent-runtime-id "$RUNTIME_ID" \
        --no-cli-pager --output json 2>/dev/null | \
        jq -r '.agentRuntimeEndpointSummaries[]? | select(.name == "${self.triggers.name}") | .agentRuntimeEndpointId' || true)

      if [ -n "$EXISTING" ]; then
        echo "Endpoint already exists: $EXISTING"
        echo "$EXISTING" > ${path.module}/endpoint_id.txt
        exit 0
      fi

      RESULT=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
        bedrock-agentcore-control create-agent-runtime-endpoint \
        --agent-runtime-id "$RUNTIME_ID" \
        --name "${self.triggers.name}" \
        --description "DevOps Copilot agent endpoint" \
        --no-cli-pager --output json)

      echo "$RESULT" | jq -r '.agentRuntimeEndpointId' > ${path.module}/endpoint_id.txt
      echo "Created endpoint: $(cat ${path.module}/endpoint_id.txt)"

      # Wait for endpoint to be ready
      ENDPOINT_ID=$(cat ${path.module}/endpoint_id.txt)
      for i in $(seq 1 30); do
        STATUS=$(aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control get-agent-runtime-endpoint \
          --agent-runtime-endpoint-id "$ENDPOINT_ID" \
          --no-cli-pager --output json | jq -r '.status')
        echo "Endpoint status: $STATUS (attempt $i/30)"
        if [ "$STATUS" = "READY" ]; then break; fi
        if [ "$STATUS" = "CREATE_FAILED" ]; then echo "FAILED"; exit 1; fi
        sleep 10
      done
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      set -e
      if [ -f ${path.module}/endpoint_id.txt ]; then
        ENDPOINT_ID=$(cat ${path.module}/endpoint_id.txt)
        echo "Deleting endpoint: $ENDPOINT_ID"
        aws --profile ${self.triggers.aws_profile} --region ${self.triggers.aws_region} \
          bedrock-agentcore-control delete-agent-runtime-endpoint \
          --agent-runtime-endpoint-id "$ENDPOINT_ID" \
          --no-cli-pager 2>/dev/null || true
        rm -f ${path.module}/endpoint_id.txt
      fi
    EOT
  }

  depends_on = [null_resource.agent_runtime]
}
