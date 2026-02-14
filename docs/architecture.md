# Architecture: AWS AgentCore + AgentGateway + Okta

## The Big Picture

This demo connects three platforms to create a secure, governed agent system:

- **AWS Bedrock AgentCore** — hosts and runs the agent container
- **AgentGateway** (on k8s-rooster) — governs LLM calls and MCP tool access with tracing, rate limiting, and security policies
- **Okta** — provides OAuth2 identity so the agent acts on behalf of authenticated users

The agent doesn't call LLMs or tools directly. Everything flows through AgentGateway, which provides a single control plane for security, observability, and policy enforcement.

## Architecture Diagram

```
                          ┌──────────────────────────────────────────────────┐
                          │            AWS Bedrock AgentCore (us-east-1)     │
                          │                                                  │
                          │  ┌────────────────────────────────────────────┐  │
                          │  │         Agent Hosting Runtime              │  │
                          │  │                                            │  │
                          │  │  ┌──────────────────────────────────────┐  │  │
                          │  │  │       DevOps Copilot Agent           │  │  │
                          │  │  │       (Python / FastAPI)             │  │  │
                          │  │  │                                      │  │  │
                          │  │  │  1. Receives /invocations request    │  │  │
                          │  │  │  2. Discovers MCP tools              │  │  │
                          │  │  │  3. Calls LLM via AgentGateway      │  │  │
                          │  │  │  4. Executes tool calls via MCP     │  │  │
                          │  │  │  5. Returns final response          │  │  │
                          │  │  └──────┬───────────────┬───────────────┘  │  │
                          │  └─────────┼───────────────┼──────────────────┘  │
                          │            │               │                     │
                          │  ┌─────────▼────┐  ┌───────▼──────────────────┐  │
                          │  │  AgentCore   │  │  AgentCore Gateway      │  │
                          │  │  Runtime     │  │  (MCP protocol)         │  │
                          │  │  Endpoint    │  │                         │  │
                          │  │              │  │  Authorizer: CUSTOM_JWT │  │
                          │  │  (invoked    │  │  (Okta OIDC discovery)  │  │
                          │  │   by users)  │  │                         │  │
                          │  └──────────────┘  │  Target: agentgateway-  │  │
                          │                    │  mcp (ngrok tunnel)     │  │
                          │                    └───────────┬─────────────┘  │
                          │                                │                │
                          │  ┌──────────────┐  ┌───────────┼─────────────┐  │
                          │  │ IAM Roles    │  │ Okta OAuth2 Credential  │  │
                          │  │ • Runtime    │  │ Provider (OBO flow)     │  │
                          │  │ • Gateway    │  └───────────┼─────────────┘  │
                          │  └──────────────┘              │                │
                          │                                │                │
                          │  ┌──────────────┐              │                │
                          │  │ ECR Repo     │              │                │
                          │  │ (arm64 img)  │              │                │
                          │  └──────────────┘              │                │
                          └────────────────────────────────┼────────────────┘
                                                           │
                          ┌────────────────────────────────┼────────────────┐
                          │        ngrok Tunnels           │                │
                          │                                │                │
                          │  mcp-agentgateway.ngrok.app ◄──┘                │
                          │       → 172.16.10.168:30168                     │
                          │                                                 │
                          │  llm-agentgateway.ngrok.app                     │
                          │       → 172.16.10.168:31572                     │
                          └────────────────────┬────────────────────────────┘
                                               │
                          ┌────────────────────┼────────────────────────────┐
                          │   k8s-rooster      │    (Talos K8s + ArgoCD)   │
                          │                    │                            │
                          │  ┌─────────────────▼────────────────────────┐   │
                          │  │          AgentGateway (Enterprise)       │   │
                          │  │                                          │   │
                          │  │  ┌─────────────────┐ ┌────────────────┐  │   │
                          │  │  │ LLM Gateway     │ │ MCP Gateway    │  │   │
                          │  │  │ (port 8080)     │ │ (port 8090)    │  │   │
                          │  │  │                 │ │                │  │   │
                          │  │  │ /anthropic/* ──►│ │ /mcp ─────────►│──┼──►│ MCP Everything
                          │  │  │   → Anthropic  │ │ /mcp/slack ───►│──┼──►│ Slack MCP
                          │  │  │ /openai/* ────►│ │ /mcp-github ──►│──┼──►│ GitHub MCP
                          │  │  │   → OpenAI    │ │                │  │   │
                          │  │  └─────────────────┘ └────────────────┘  │   │
                          │  │                                          │   │
                          │  │  Policies:  PII protection              │   │
                          │  │             Prompt injection guard       │   │
                          │  │             Credential leak protection   │   │
                          │  │             Rate limiting (xAI)         │   │
                          │  │                                          │   │
                          │  │  Tracing:   → Langfuse (OTLP)           │   │
                          │  │             → ClickHouse (Solo UI)      │   │
                          │  └──────────────────────────────────────────┘   │
                          └────────────────────────────────────────────────┘

                          ┌────────────────────────────────────────────────┐
                          │                    Okta                        │
                          │                                                │
                          │  Org: integrator-7147223.okta.com              │
                          │                                                │
                          │  ┌──────────────────┐  ┌───────────────────┐   │
                          │  │ devops-copilot-  │  │ devops-copilot-  │   │
                          │  │ client           │  │ service          │   │
                          │  │ (auth code flow) │  │ (client creds)   │   │
                          │  └──────────────────┘  └───────────────────┘   │
                          │                                                │
                          │  Scopes: mcp:read, mcp:write, mcp:admin        │
                          │  Auth Server: default (aus104zseyg64swj3698)    │
                          │  Policy: AgentCore Policy + Allow MCP scopes   │
                          └────────────────────────────────────────────────┘
```

## Request Flow

### 1. User Invokes Agent

```
User/App → AWS AgentCore → POST /invocations → Agent Container
```

The user (or application) calls the AgentCore Runtime Endpoint. AgentCore spins up the agent container and forwards the request to `/invocations` on port 8080.

### 2. Agent Discovers Tools

```
Agent → MCP Gateway (ngrok) → AgentGateway → MCP Servers
  POST /mcp          → initialize + tools/list → Everything tools
  POST /mcp/slack    → initialize + tools/list → Slack tools  
  POST /mcp-github   → initialize + tools/list → GitHub tools
```

The agent calls each MCP endpoint to discover available tools. These are converted to OpenAI function-calling format for the LLM.

### 3. Agent Calls LLM

```
Agent → LLM Gateway (ngrok) → AgentGateway → Anthropic API
  POST /anthropic/v1/chat/completions
    model: claude-sonnet-4-20250514
    messages: [system prompt + user input]
    tools: [discovered MCP tools in OpenAI format]
```

The agent sends the user's request plus available tools to Claude via AgentGateway. AgentGateway applies policies (PII protection, prompt injection guard) and traces the request to Langfuse.

### 4. Agent Executes Tool Calls

If the LLM decides to use a tool:

```
LLM response: tool_calls: [{name: "slack_post_message", arguments: {...}}]
  → Agent routes to /mcp/slack (based on tool discovery map)
  → MCP tools/call → Slack MCP server → Slack API
  → Result fed back to LLM
```

The agent maintains a routing map from tool discovery, so each tool call goes to the correct MCP endpoint.

### 5. Final Response

The LLM produces a final text response (no more tool calls), which flows back:

```
Agent → AgentCore → User/App
```

## Auth Flow (Okta)

```
┌──────┐     ┌──────┐     ┌───────────┐     ┌─────────────┐     ┌──────────┐
│ User │────►│ Okta │────►│ AgentCore │────►│ AgentGateway│────►│ MCP Tools│
│      │     │      │     │  Gateway  │     │             │     │          │
│      │ 1.  │      │ 2.  │           │ 3.  │             │ 4.  │          │
│      │Auth │      │JWT  │ Validates │     │ Token       │     │ Delegated│
│      │Code │      │Token│ via OIDC  │     │ Validation  │     │ Identity │
│      │Flow │      │     │ Discovery │     │ (in case    │     │          │
│      │     │      │     │           │     │  OAuth)     │     │          │
└──────┘     └──────┘     └───────────┘     └─────────────┘     └──────────┘
```

1. **User authenticates** with Okta (authorization code + PKCE flow)
2. **Okta issues JWT** with MCP scopes (`mcp:read`, `mcp:write`, `mcp:admin`)
3. **AgentCore Gateway validates** the JWT using Okta's OIDC discovery URL
4. **AgentGateway validates** the token for MCP tool access (on-behalf-of)

## Infrastructure Components

### Terraform-Managed (AWS)

| Resource | Type | Description |
|----------|------|-------------|
| `aws_ecr_repository.agent` | Native TF | Container image repository |
| `aws_iam_role.agentcore_gateway` | Native TF | Gateway service role (logs, secrets) |
| `aws_iam_role.agentcore_runtime` | Native TF | Runtime role (ECR pull, Bedrock, logs) |
| `null_resource.gateway` | local-exec CLI | AgentCore MCP gateway with Okta JWT auth |
| `null_resource.gateway_target_mcp` | local-exec CLI | Gateway target → ngrok → AgentGateway |
| `null_resource.agent_runtime` | local-exec CLI | Agent container runtime (arm64) |
| `null_resource.agent_runtime_endpoint` | local-exec CLI | Public invocation endpoint |
| `null_resource.okta_credential_provider` | local-exec CLI | Okta OAuth2 for OBO flow |

### Terraform-Managed (Okta)

| Resource | Type | Description |
|----------|------|-------------|
| `okta_app_oauth.agentcore_client` | Native TF | User-facing app (auth code + refresh) |
| `okta_app_oauth.agentcore_service` | Native TF | Agent service app (client credentials) |
| `okta_auth_server_scope.mcp_*` | Native TF | MCP scopes (read, write, admin) |
| `okta_auth_server_policy.agentcore` | Native TF | Token policy for both apps |
| `okta_auth_server_policy_rule.*` | Native TF | Allow MCP scopes for Everyone group |

### k8s-rooster (ArgoCD-Managed)

| Component | Namespace | Description |
|-----------|-----------|-------------|
| AgentGateway Proxy | agentgateway-system | LLM gateway (port 8080/31572) |
| MCP Gateway Proxy | agentgateway-system | Consolidated MCP gateway (port 8090/30168) |
| Slack MCP Server | agentgateway-system | Slack tool server |
| GitHub MCP Backend | agentgateway-system | GitHub Copilot MCP (api.githubcopilot.com) |
| MCP Everything | agentgateway-system | Demo MCP tools |
| Langfuse OTel Collector | agentgateway-system | Trace fan-out to Langfuse + ClickHouse |
| Security Policies | agentgateway-system | PII, prompt injection, credential protection |

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| **arm64 images only** | AgentCore runtime only supports arm64 architecture |
| **CUSTOM_JWT at creation** | Gateway authorizer type cannot be changed after creation |
| **Consolidated MCP gateway** | Single port (30168) for all MCP tools → single ngrok tunnel |
| **`null_resource` + CLI** | No Terraform provider for AgentCore yet |
| **ngrok for tunneling** | Connects AWS to on-prem k8s-rooster securely |
| **Agent loop pattern** | Discover tools → LLM → tool calls → LLM → response |
| **Path-based LLM routing** | `/anthropic/v1/*` and `/openai/v1/*` on LLM gateway |

## Tracing & Observability

Every request through AgentGateway is traced via OpenTelemetry. A fan-out OTel Collector duplicates traces to two backends simultaneously:

```
Agent → AgentGateway → OTel Collector (fan-out)
                           ├──► Langfuse (OTLP HTTP) — LLM-native observability
                           │      • Token usage, cost tracking
                           │      • Prompt/completion logging
                           │      • Trace waterfall with tool calls
                           │      • Self-hosted at http://172.16.10.173:3000
                           │
                           └──► ClickHouse (Solo UI) — AgentGateway-native dashboards
                                  • Gateway metrics and route analytics
                                  • Policy evaluation results
                                  • Rate limiting stats
```

### What Gets Captured

| Signal | Source | Destination |
|--------|--------|-------------|
| LLM request/response spans | AgentGateway proxy | Langfuse + ClickHouse |
| MCP tool call spans | AgentGateway MCP gateway | Langfuse + ClickHouse |
| Policy evaluation (PII, injection) | AgentGateway policies | ClickHouse (Solo UI) |
| Token usage & model info | AgentGateway proxy | Langfuse |
| Gateway route/endpoint metadata | AgentGateway | Both |

### Why Dual Export?

- **Langfuse** gives LLM-focused observability: cost tracking, prompt analysis, trace waterfalls with tool call chains — ideal for debugging agent behavior
- **ClickHouse (Solo UI)** gives infrastructure-focused observability: gateway metrics, policy enforcement stats, rate limiting — ideal for ops

The fan-out collector is a separate OTel Collector deployment that avoids conflicts with AgentGateway's Helm-managed ConfigMap (managed by ArgoCD).
