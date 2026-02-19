# AWS Bedrock AgentCore + AgentGateway + Okta Demo

AI agents calling LLMs and tools directly means no visibility, no security policies, and no cost control. This demo puts [AgentGateway](https://github.com/agentgateway/agentgateway) between your agents and everything they talk to — giving you the same governance for AI that API gateways gave to microservices.

**Key design choice:** AgentGateway handles ALL authentication and governance. No vendor-specific gateway needed. AgentCore provides compute — AgentGateway provides control.

[Read the full writeup →](docs/blog-why-agent-gateway.md)

Deploy a DevOps Copilot agent on AWS Bedrock AgentCore with:

- **[AgentGateway](https://github.com/agentgateway/agentgateway)** — LLM proxy + MCP tool gateway with JWT auth, RBAC, tracing, rate limiting, PII protection, and prompt injection guards
- **[Okta](https://developer.okta.com)** — OAuth2 identity (client_credentials for agent → AgentGateway)
- **[ngrok](https://ngrok.com)** — secure tunneling from AWS to on-prem Kubernetes
- **[Langfuse](https://langfuse.com) + ClickHouse** — dual-export observability

## Architecture

```
┌──────────────────────────────────────────────────┐
│           AWS Bedrock AgentCore (us-east-1)       │
│                                                    │
│  ┌──────────────────────────────────────────────┐ │
│  │        DevOps Copilot Agent                   │ │
│  │        (Python / FastAPI / arm64)             │ │
│  │                                               │ │
│  │  POST /invocations                            │ │
│  │  → Get Okta JWT (client_credentials)          │ │
│  │  → Discover MCP tools (JWT auth)              │ │
│  │  → Call LLM (no auth, AG has keys)            │ │
│  │  → Execute tool calls (JWT auth)              │ │
│  │  → Return response                            │ │
│  └───────────┬──────────────┬────────────────────┘ │
│              │              │                       │
│  ┌───────────▼──┐           │                       │
│  │   Runtime     │           │                       │
│  │   Endpoint    │           │                       │
│  └──────────────┘           │                       │
└─────────────────────────────┼───────────────────────┘
                              │ ngrok tunnels
       ┌──────────────────────┼────────────────┐
       │     mcp: → :30168    │  llm: → :31572 │
       └──────────────────────┼────────────────┘
                              │
       ┌──────────────────────▼────────────────┐
       │    k8s-rooster (Talos + ArgoCD)        │
       │                                        │
       │    AgentGateway (Enterprise)            │
       │    ├─ LLM: /anthropic/* → Claude       │
       │    │       /openai/* → GPT             │
       │    ├─ MCP: /mcp → Everything           │
       │    │       /mcp/slack → Slack           │
       │    │       /mcp-github → GitHub         │
       │    ├─ Auth: Okta JWT (Strict mode)      │
       │    │   └─ Scope-based RBAC on MCP       │
       │    ├─ Policies: PII, injection,         │
       │    │   credential leak, rate limits      │
       │    └─ Traces: → Langfuse + ClickHouse   │
       └────────────────────────────────────────┘
```

## What's Deployed

| Layer | Component | Details |
|-------|-----------|---------|
| Identity | Okta | Service app (client_credentials), custom MCP scopes |
| Hosting | AgentCore Runtime | arm64 container, FastAPI agent with LLM + MCP loop |
| Tunneling | ngrok | 2 static domains → on-prem k8s (MCP + LLM) |
| **Governance** | **AgentGateway** | **LLM proxy + MCP gateway + JWT auth + RBAC + security policies** |
| Observability | Langfuse + ClickHouse | Dual OTel export via fan-out collector |
| Infra | Terraform + ArgoCD | AWS/Okta via TF, k8s via ArgoCD GitOps |

## Guardrails

AgentGateway enforces these policies on every request:

| Category | Policy | What It Does |
|----------|--------|-------------|
| **Auth** | JWT Authentication | Validates Okta JWTs on MCP routes (Strict mode) |
| **Auth** | Scope-Based RBAC | `mcp:read` → list/search, `mcp:write` → create/post, `mcp:admin` → full |
| **Auth** | Destructive Op Blocking | `delete_*`, `merge_pull_request` always denied |
| Security | PII Protection | Detects/redacts PII before it reaches the LLM |
| Security | Prompt Injection Guard | Blocks jailbreak and manipulation attempts |
| Security | Credential Leak Protection | Prevents API keys/tokens from leaking in responses |
| Traffic | Rate Limiting | Per-identity request + token limits |
| Traffic | Path-based Routing | /anthropic/* → Claude, /openai/* → GPT, same gateway |
| Observability | Dual Trace Export | Every LLM + MCP call traced to Langfuse AND ClickHouse |

## Auth Flow

```
Invoker → IAM (invoke-agent-runtime) → AgentCore Runtime → Agent
    Agent → Okta (client_credentials) → JWT with MCP scopes
    Agent → AgentGateway LLM (no auth, AG holds API keys)
    Agent → AgentGateway MCP (Bearer JWT) → JWT validated → scope RBAC → tools
```

## Quick Start

### 1. Configure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Set: okta_org_name, okta_api_token
```

### 2. Deploy Infrastructure

```bash
terraform init
terraform apply  # Creates Okta apps + AWS runtime/IAM/ECR
```

### 3. Apply AgentGateway Auth Policy

```bash
kubectl apply -f k8s/agentgateway-auth-policy.yaml
```

### 4. Build & Push Agent (arm64 required)

```bash
cd agent
aws --profile agentcore-demo ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/arm64 \
  -t <account>.dkr.ecr.us-east-1.amazonaws.com/devops-copilot-agent:latest \
  --push .
```

### 5. Configure Agent Environment

Set these on the agent container (via AgentCore runtime config or env):

```bash
LLM_GATEWAY_URL=https://llm-agentgateway.ngrok.app
MCP_GATEWAY_URL=https://mcp-agentgateway.ngrok.app
OKTA_TOKEN_URL=<from terraform output okta_token_url>
OKTA_CLIENT_ID=<from terraform output okta_service_client_id>
OKTA_CLIENT_SECRET=<from terraform output -raw okta_service_client_secret>
OKTA_SCOPES="mcp:read mcp:write"
```

### 6. Start ngrok Tunnels

```yaml
# ngrok.yml
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

### 7. Test

```bash
RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:<account>:runtime/<runtime-id>"
PAYLOAD=$(echo -n '{"input":"List available Slack channels"}' | base64 -w0)

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --content-type "application/json" \
  --payload "$PAYLOAD" \
  response.json
```

## Project Structure

```
├── terraform/              # Okta + AWS infrastructure
│   ├── okta.tf            # OAuth2 apps, scopes, policies
│   ├── agentcore.tf       # ECR + Runtime + Endpoint
│   ├── iam.tf             # IAM roles (runtime only)
│   └── variables.tf       # Input variables
├── agent/                  # Agent application
│   ├── agent.py           # DevOps Copilot (LLM + MCP + Okta auth)
│   ├── Dockerfile         # arm64-compatible container
│   └── requirements.txt
├── k8s/                    # Kubernetes resources
│   └── agentgateway-auth-policy.yaml  # JWT auth + RBAC for MCP
└── docs/
    ├── architecture.md    # Detailed architecture + diagrams
    └── blog-why-agent-gateway.md  # Why you need a gateway
```

## Key Gotchas

| Gotcha | Detail |
|--------|--------|
| arm64 only | AgentCore requires arm64 images — use `docker buildx --platform linux/arm64` |
| ngrok headers | Agent sets `ngrok-skip-browser-warning: true` to bypass interstitial |
| MCP Accept header | Must include `application/json, text/event-stream` (406 otherwise) |
| Token caching | Agent caches Okta tokens with 5-min buffer before expiry |
| Enterprise required | JWT auth on AgentGateway requires Enterprise (`EnterpriseAgentgatewayPolicy`) |
