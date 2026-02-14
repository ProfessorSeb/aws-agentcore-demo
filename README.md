# AWS Bedrock AgentCore Demo

Deploy a **DevOps Copilot** agent on AWS Bedrock AgentCore, connected to AgentGateway on k8s-rooster for LLM and MCP tool access.

## Architecture

```
AgentCore Runtime (container) → AgentCore Gateway (MCP) → AgentGateway (k8s-rooster) → LLMs + Tools
```

See [docs/architecture.md](docs/architecture.md) for the full diagram.

## Prerequisites

- **AWS CLI** v2 with `agentcore-demo` profile configured
- **Terraform** >= 1.5
- **Docker** (for building the agent container)
- **jq** (for script output parsing)

## Quick Start

### 1. Configure Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set agentgateway_endpoint to your public URL
```

### 2. Deploy Everything

```bash
./scripts/deploy.sh
```

This will:
1. Create IAM roles and ECR repository (Terraform)
2. Build and push the agent container to ECR
3. Create AgentCore runtime, endpoint, gateway, and targets (Terraform via AWS CLI)

### 3. Test

```bash
./scripts/test.sh
```

### 4. Destroy

```bash
./scripts/destroy.sh
```

## Project Structure

```
├── terraform/          # Infrastructure as Code
│   ├── main.tf         # Provider config
│   ├── iam.tf          # IAM roles for AgentCore
│   ├── agentcore.tf    # ECR + Runtime + Endpoint (local-exec)
│   ├── gateway.tf      # Gateway + Targets (local-exec)
│   ├── credentials.tf  # OAuth2/API key placeholders
│   ├── variables.tf    # Input variables
│   ├── outputs.tf      # Outputs
│   └── versions.tf     # Provider versions
├── agent/              # Agent application
│   ├── agent.py        # DevOps Copilot agent (FastAPI)
│   ├── Dockerfile      # Container image
│   └── requirements.txt
├── scripts/            # Deployment scripts
│   ├── deploy.sh       # Full deploy
│   ├── destroy.sh      # Tear down
│   └── test.sh         # Status check
└── docs/
    └── architecture.md # Architecture diagram
```

## Why `null_resource` + `local-exec`?

AWS Bedrock AgentCore is brand new — no Terraform provider resources exist yet. We use `null_resource` with `local-exec` provisioners calling the AWS CLI (`bedrock-agentcore-control` subcommand). This is structured cleanly so resources can be migrated to native Terraform resources when a provider is available.

## AgentGateway Connection

The AgentCore Gateway points to your AgentGateway instance on k8s-rooster. Since k8s-rooster is on a private network (172.16.10.168), you need a public endpoint:

- **Option 1**: ngrok tunnel to the AgentGateway service
- **Option 2**: Cloudflare tunnel
- **Option 3**: Public load balancer

Set the public URL in `terraform.tfvars` → `agentgateway_endpoint`.

## Future: Okta OBO Integration

The `credentials.tf` file has a placeholder for OAuth2 credential provider integration with Okta. When ready:

1. Configure Okta OIDC application
2. Create OAuth2 credential provider in AgentCore
3. Attach credential provider to gateway targets
4. Enable on-behalf-of (OBO) token flow

## AWS Profile

All commands use `--profile agentcore-demo`. Set this up:

```bash
aws configure --profile agentcore-demo
# Region: us-east-1
# Account: 103739863673
```
