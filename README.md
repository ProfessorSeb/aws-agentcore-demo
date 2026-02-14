# AWS Bedrock AgentCore + AgentGateway + Okta Demo

> **Why a gateway?** AI agents calling LLMs and tools directly means no visibility, no security policies, and no cost control. This demo puts [AgentGateway](https://github.com/agentgateway/agentgateway) between your agents and everything they talk to — giving you the same governance for AI that API gateways gave to microservices. [Read the full writeup →](docs/blog-why-agent-gateway.md)

Deploy a **DevOps Copilot** agent on AWS Bedrock AgentCore with:
- **[AgentGateway](https://github.com/agentgateway/agentgateway)** — LLM proxy + MCP tool gateway with tracing, rate limiting, PII protection, and prompt injection guards
- **[Okta](https://developer.okta.com)** — OAuth2 identity with on-behalf-of token flow
- **[ngrok](https://ngrok.com)** — secure tunneling from AWS to on-prem Kubernetes
- **[Langfuse](https://langfuse.com)** + **ClickHouse** — dual-export observability (LLM traces + gateway metrics)

## Architecture

```
┌──────────────────────────────────────────────────┐
│        AWS Bedrock AgentCore (us-east-1)         │
│                                                  │
│   ┌──────────────────────────────────────────┐   │
│   │         DevOps Copilot Agent             │   │
│   │         (Python / FastAPI / arm64)       │   │
│   │                                          │   │
│   │   POST /invocations                      │   │
│   │     → Discover MCP tools                 │   │
│   │     → Call LLM (via AgentGateway)        │   │
│   │     → Execute tool calls (via MCP)       │   │
│   │     → Return response                   │   │
│   └───────────┬──────────────┬───────────────┘   │
│               │              │                   │
│   ┌───────────▼──┐   ┌──────▼───────────────┐   │
│   │  Runtime     │   │  Gateway (MCP)       │   │
│   │  Endpoint    │   │  Okta CUSTOM_JWT     │   │
│   └──────────────┘   └──────────┬───────────┘   │
└──────────────────────────────────┼───────────────┘
                                   │
              ┌────────────────────┼────────────────┐
              │   ngrok Tunnels    │                 │
              │   mcp: → :30168   │   llm: → :31572 │
              └────────────────────┼────────────────┘
                                   │
              ┌────────────────────▼────────────────┐
              │   k8s-rooster (Talos + ArgoCD)      │
              │                                     │
              │   AgentGateway                      │
              │   ├─ LLM:  /anthropic/* → Claude    │
              │   │        /openai/*   → GPT        │
              │   ├─ MCP:  /mcp        → Everything │
              │   │        /mcp/slack  → Slack      │
              │   │        /mcp-github → GitHub     │
              │   ├─ Policies: PII, injection,      │
              │   │   credential leak, rate limits   │
              │   └─ Traces: → Langfuse + ClickHouse│
              └─────────────────────────────────────┘
```

## What's Deployed

| Layer | Component | Details |
|-------|-----------|---------|
| **Identity** | Okta | 2 OAuth2 apps, custom scopes (`mcp:read/write/admin`), auth server policy |
| **Hosting** | AgentCore Runtime | arm64 container, FastAPI agent with LLM + MCP loop |
| **Routing** | AgentCore Gateway | MCP protocol gateway with Okta CUSTOM_JWT authorizer |
| **Tunneling** | ngrok | 2 static domains → on-prem k8s (MCP + LLM) |
| **Governance** | AgentGateway | LLM proxy + MCP gateway with security policies |
| **Observability** | Langfuse + ClickHouse | Dual OTel export via fan-out collector |
| **Infra** | Terraform + ArgoCD | AWS/Okta via TF, k8s via ArgoCD GitOps |

## Guardrails

AgentGateway enforces these policies on every request:

| Category | Policy | What It Does |
|----------|--------|-------------|
| **Security** | PII Protection | Detects/redacts PII before it reaches the LLM |
| **Security** | Prompt Injection Guard | Blocks jailbreak and manipulation attempts |
| **Security** | Credential Leak Protection | Prevents API keys/tokens from leaking in responses |
| **Security** | MCP JWT Authentication | Validates Okta JWTs on MCP routes — unauthenticated requests rejected |
| **Security** | Scope-Based MCP RBAC | `mcp:read` → list/search only, `mcp:write` → create/post, `mcp:admin` → full access |
| **Security** | Destructive Op Blocking | `delete_repository`, `merge_pull_request` always denied regardless of scope |
| **Traffic** | Rate Limiting | Per-user request + token limits (e.g., 10 req/min, 5K tokens/min) |
| **Traffic** | Path-based Routing | `/anthropic/*` → Claude, `/openai/*` → GPT, same gateway |
| **Observability** | Dual Trace Export | Every LLM + MCP call traced to Langfuse AND ClickHouse |
| **Identity** | Okta OAuth2 OBO | Tools execute with delegated user identity |

## Agent Capabilities

The agent (`agent/agent.py` v0.2.0) implements a full agentic loop:

1. **Discovers MCP tools** from all endpoints (Slack, GitHub, Everything)
2. **Calls LLM** via AgentGateway's OpenAI-compatible API
3. **Executes tool calls** via MCP through AgentGateway
4. **Iterates** (up to 5 rounds) until the LLM produces a final response

### Endpoints

| Type | Path | Backend |
|------|------|---------|
| LLM | `/anthropic/v1/chat/completions` | Claude via Anthropic |
| LLM | `/openai/v1/chat/completions` | GPT via OpenAI |
| MCP | `/mcp` | Everything MCP server |
| MCP | `/mcp/slack` | Slack (post_message, list_channels, ...) |
| MCP | `/mcp-github` | GitHub Copilot (issues, PRs, repos, ...) |

## Quick Start

### 1. Configure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Set: okta_org_name, okta_api_token, agentgateway_endpoint
```

### 2. Deploy Infrastructure

```bash
terraform init
terraform apply   # Creates Okta apps + AWS gateway/runtime/IAM/ECR
```

### 3. Build & Push Agent (arm64 required)

```bash
cd agent
aws --profile agentcore-demo ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/arm64 \
  -t <account>.dkr.ecr.us-east-1.amazonaws.com/devops-copilot-agent:latest \
  --push .
```

### 4. Start ngrok Tunnels

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

### 5. Test

```bash
# Invoke the agent via AgentCore
RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:<account>:runtime/<runtime-id>"
PAYLOAD=$(echo -n '{"input":"List available Slack channels"}' | base64 -w0)

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --content-type "application/json" \
  --payload "$PAYLOAD" \
  response.json
```

## Auth Flow

```
User → Okta (auth code + PKCE) → JWT with MCP scopes
  → AgentCore Gateway (validates JWT via OIDC discovery)
    → Agent Runtime (processes request)
      → AgentGateway LLM (OpenAI-compatible, via ngrok)
      → AgentGateway MCP (Slack/GitHub tools, via ngrok)
        → Tools execute with delegated user identity
```

## Project Structure

```
├── terraform/              # Okta + AWS infrastructure
│   ├── okta.tf             # OAuth2 apps, scopes, policies
│   ├── gateway.tf          # AgentCore Gateway + MCP target
│   ├── agentcore.tf        # ECR + Runtime + Endpoint
│   ├── iam.tf              # IAM roles
│   ├── credentials.tf      # Okta credential provider (OBO)
│   └── variables.tf        # Input variables
├── agent/                  # Agent application
│   ├── agent.py            # DevOps Copilot (LLM + MCP loop)
│   ├── Dockerfile          # arm64-compatible container
│   └── requirements.txt
└── docs/
    ├── architecture.md     # Detailed architecture + diagrams
    └── blog-why-agent-gateway.md  # Why you need a gateway
```

## Key Gotchas

| Gotcha | Detail |
|--------|--------|
| **arm64 only** | AgentCore requires arm64 images — use `docker buildx --platform linux/arm64` |
| **Immutable authorizer** | Gateway authorizer type can't change after creation — set `CUSTOM_JWT` from the start |
| **`/invocations` path** | AgentCore calls `/invocations` (SageMaker convention), not `/invoke` |
| **No TF provider** | AgentCore has no Terraform provider yet — using `null_resource` + AWS CLI |
| **ngrok interstitial** | Add `ngrok-skip-browser-warning` header for programmatic access |

## Observability

```
Agent → AgentGateway → OTel Collector (fan-out)
                           ├──► Langfuse — cost tracking, prompt logging, trace waterfalls
                           └──► ClickHouse — gateway metrics, policy stats, route analytics
```

Both backends receive every LLM call and MCP tool invocation in real-time. See [architecture.md](docs/architecture.md) for details.

## MCP Tool Access Control

AgentGateway enforces authentication and authorization at the MCP route level:

```yaml
# JWT Authentication — validates Okta tokens on every MCP request
apiVersion: enterpriseagentgateway.solo.io/v1alpha1
kind: EnterpriseAgentgatewayPolicy
metadata:
  name: mcp-jwt-auth-ent
spec:
  targetRefs:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: mcp-slack
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: mcp-github
  traffic:
    jwtAuthentication:
      mode: Strict
      providers:
      - issuer: "https://integrator-7147223.okta.com/oauth2/aus104zseyg64swj3698"
        audiences: ["api://default"]
        jwks:
          inline: '<Okta JWKS JSON>'
```

```yaml
# Scope-Based RBAC — CEL expressions match JWT scopes to allowed tools
apiVersion: agentgateway.dev/v1alpha1
kind: AgentgatewayPolicy
metadata:
  name: mcp-tool-rbac-read
spec:
  backend:
    mcp:
      authorization:
        action: Allow
        policy:
          matchExpressions:
          - >-
            claims.scp.exists(s, s == 'mcp:read') && (
              tool.name.startsWith('list_') ||
              tool.name.startsWith('get_') ||
              tool.name.startsWith('search_')
            )
```

See [auth-flow-deep-dive.md](docs/auth-flow-deep-dive.md) for the complete policy set.

## Related

| Resource | Link |
|----------|------|
| AgentGateway (CNCF) | https://github.com/agentgateway/agentgateway |
| k8s-rooster (backing cluster) | https://github.com/ProfessorSeb/k8s-rooster |
| Why you need a gateway (blog) | [docs/blog-why-agent-gateway.md](docs/blog-why-agent-gateway.md) |
| Architecture deep-dive | [docs/architecture.md](docs/architecture.md) |
