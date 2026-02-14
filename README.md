# AWS Bedrock AgentCore + AgentGateway + Okta Demo

Deploy a **DevOps Copilot** agent on AWS Bedrock AgentCore with:
- **AgentGateway** for LLM proxy + MCP tool access (with tracing, rate limiting, security policies)
- **Okta** for OAuth2 identity (on-behalf-of auth flow)
- **ngrok** for secure tunneling to on-prem k8s-rooster cluster

## Architecture

```
┌─────────────────────────────────────────┐
│           AWS Bedrock AgentCore         │
│  ┌─────────────────────────────────┐    │
│  │     Agent Hosting Runtime       │    │
│  │  ┌───────────────────────────┐  │    │
│  │  │    DevOps Copilot Agent   │  │    │
│  │  │         (Python)          │  │    │
│  │  └──────┬──────────┬─────────┘  │    │
│  └─────────┼──────────┼────────────┘    │
│            │          │                 │
│     mTLS + │    AUTH   │                │
│     API key│ Mechanism │                │
└────────────┼──────────┼────────────────┘
             │          │
     ┌───────▼──┐  ┌────▼──────────┐     ┌──────────┐
     │agentgw   │  │  agentgw      │     │          │
     │  LLM     │  │  MCP/Tools    │     │  OKTA    │
     │(Anthropic│  │(Slack/GitHub) │◄────│  (JWT)   │
     │ OpenAI)  │  │               │     │          │
     └────┬─────┘  └──────┬────────┘     └──────────┘
          │               │
     ┌────▼─────┐   ┌─────▼──────┐
     │  LLMs    │   │   Tools    │
     │Claude,GPT│   │Slack,GitHub│
     └──────────┘   └────────────┘
```

## What's Deployed

| Component | Details |
|---|---|
| **Okta** | 2 OAuth2 apps, 3 MCP scopes (`mcp:read`, `mcp:write`, `mcp:admin`), auth server policy |
| **AWS Gateway** | AgentCore MCP gateway with Okta CUSTOM_JWT authorizer |
| **Gateway Target** | Points to AgentGateway MCP endpoint via ngrok |
| **Agent Runtime** | arm64 container on AgentCore (FastAPI + httpx) |
| **IAM Roles** | Gateway role + Runtime role (Bedrock, ECR, CloudWatch, Secrets Manager) |
| **ECR** | `devops-copilot-agent` repository |
| **ngrok Tunnels** | `mcp-agentgateway.ngrok.app` (MCP) + `llm-agentgateway.ngrok.app` (LLM) |

## Agent Capabilities

The agent (`agent/agent.py`) implements a full agent loop:

1. **Discovers MCP tools** from all endpoints (Slack, GitHub, Everything)
2. **Calls LLM** via AgentGateway's OpenAI-compatible API
3. **Executes tool calls** via MCP through AgentGateway
4. **Iterates** until the LLM produces a final response

### MCP Endpoints (consolidated on port 8090/30168)

| Path | Backend | Tools |
|---|---|---|
| `/mcp` | Everything MCP server | echo, add, longRunningOperation, ... |
| `/mcp/slack` | Slack MCP | post_message, list_channels, ... |
| `/mcp-github` | GitHub Copilot MCP | issues, PRs, repos, ... |

### LLM Endpoint

| Path | Backend |
|---|---|
| `/anthropic/v1/chat/completions` | Claude (via Anthropic API) |
| `/openai/v1/chat/completions` | GPT (via OpenAI API) |

## Prerequisites

- **AWS CLI** v2 with `agentcore-demo` profile configured
- **Terraform** >= 1.5
- **Docker** with buildx (for arm64 cross-compilation)
- **Okta** developer account
- **ngrok** (paid plan for multiple tunnels + static domains)

## Quick Start

### 1. Configure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Set: okta_org_name, okta_api_token, agentgateway_endpoint
```

### 2. Deploy Okta + AWS Infrastructure

```bash
terraform init
terraform apply
```

### 3. Build & Push Agent (arm64)

```bash
cd agent
# Login to ECR
aws --profile agentcore-demo ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 103739863673.dkr.ecr.us-east-1.amazonaws.com

# Build arm64 and push (AgentCore requires arm64)
docker buildx build --platform linux/arm64 \
  -t 103739863673.dkr.ecr.us-east-1.amazonaws.com/devops-copilot-agent:latest \
  --push .
```

### 4. Start ngrok Tunnels

```yaml
# ~/.config/ngrok/ngrok.yml
version: "3"
tunnels:
  mcp:
    addr: 172.16.10.168:30168
    proto: http
    url: mcp-agentgateway.ngrok.app
  llm:
    addr: 172.16.10.168:31572
    proto: http
    url: llm-agentgateway.ngrok.app
```

```bash
ngrok start --all
```

### 5. Test

```bash
# Check agent health
curl https://mcp-agentgateway.ngrok.app/mcp  # Should return 406 (expected)

# Check LLM gateway
curl https://llm-agentgateway.ngrok.app/anthropic/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

# List discovered tools
curl http://<agent-endpoint>/tools
```

## Project Structure

```
├── terraform/              # Infrastructure as Code
│   ├── main.tf             # AWS provider + locals
│   ├── versions.tf         # Provider versions (AWS, Okta, null)
│   ├── variables.tf        # Input variables
│   ├── outputs.tf          # Outputs
│   ├── iam.tf              # IAM roles for AgentCore
│   ├── agentcore.tf        # ECR + Runtime + Endpoint
│   ├── gateway.tf          # AgentCore Gateway + MCP Target
│   ├── okta.tf             # Okta apps, scopes, policies
│   └── credentials.tf      # Okta OAuth2 credential provider
├── agent/                  # Agent application
│   ├── agent.py            # DevOps Copilot agent (LLM + MCP loop)
│   ├── Dockerfile          # arm64-compatible container
│   └── requirements.txt
├── scripts/                # Deployment scripts
└── docs/
    └── architecture.md     # Detailed architecture
```

## Auth Flow

```
User → Okta (authorization_code) → JWT token
  → AgentCore (validates JWT via CUSTOM_JWT authorizer)
    → Agent Runtime (processes request)
      → AgentGateway LLM (via ngrok, OpenAI-compatible)
      → AgentGateway MCP (via ngrok, Okta token validation)
        → Slack/GitHub tools (with delegated identity)
```

## Key Decisions

- **AgentCore requires arm64**: Use `docker buildx --platform linux/arm64` for cross-compilation
- **Gateway authorizer is immutable**: Must set `CUSTOM_JWT` at creation time (can't update from `NONE`)
- **Consolidated MCP gateway**: All MCP tools (Slack, GitHub, Everything) on one gateway/port for single ngrok tunnel
- **`null_resource` + `local-exec`**: No Terraform provider for AgentCore yet — using AWS CLI
- **Okta `refresh_token` not a valid grant type in policy rules**: Implied by `authorization_code`
- **Okta policy rules need group assignment**: Added "Everyone" group for `authorization_code` grant

## Related

- [k8s-rooster](https://github.com/ProfessorSeb/k8s-rooster) — Talos K8s cluster with ArgoCD, AgentGateway, kagent
- [AgentGateway](https://github.com/agentgateway/agentgateway) — CNCF open-source agent gateway
