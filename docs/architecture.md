# Architecture: AWS AgentCore + AgentGateway + Okta

## The Big Picture

This demo connects three platforms to create a secure, governed agent system:

- **AWS Bedrock AgentCore** — hosts and runs the agent container (compute only)
- **AgentGateway** (Enterprise, on k8s-rooster) — governs LLM calls and MCP tool access with auth, RBAC, tracing, rate limiting, and security policies
- **Okta** — provides OAuth2 identity via client_credentials so the agent authenticates to AgentGateway

**Key design choice:** No AgentCore Gateway. AgentGateway handles ALL authentication and governance. AWS provides compute, AgentGateway provides control. This makes the architecture portable — the same AgentGateway policies work on AWS, GCP, Azure, or bare metal.

## Architecture Diagram

```
┌──────────────────────────────────────────────────┐
│           AWS Bedrock AgentCore (us-east-1)       │
│                                                    │
│  ┌──────────────────────────────────────────────┐ │
│  │        DevOps Copilot Agent                   │ │
│  │        (Python / FastAPI / arm64)             │ │
│  │                                               │ │
│  │  1. Receives /invocations request             │ │
│  │  2. Gets Okta JWT (client_credentials)        │ │
│  │  3. Discovers GitHub MCP tools (JWT auth)     │ │
│  │  4. Calls LLM via AgentGateway (no auth)      │ │
│  │  5. Executes tool calls via MCP (JWT auth)    │ │
│  │  6. Returns final response                    │ │
│  └──────┬───────────────┬────────────────────────┘ │
│         │               │                          │
│  ┌──────▼────┐          │                          │
│  │ Runtime   │    No AgentCore Gateway             │
│  │ Endpoint  │    (removed — AG handles auth)      │
│  └───────────┘          │                          │
│                         │                          │
│  ┌──────────┐  ┌────────┼──────────┐               │
│  │ IAM Role │  │ ECR Repo (arm64)  │               │
│  │ (runtime)│  └───────────────────┘               │
│  └──────────┘           │                          │
└─────────────────────────┼──────────────────────────┘
                          │ ngrok tunnels
   ┌──────────────────────┼────────────────┐
   │  mcp-agentgateway.ngrok.app → :30168  │
   │  llm-agentgateway.ngrok.app → :31572  │
   └──────────────────────┼────────────────┘
                          │
   ┌──────────────────────▼────────────────────────┐
   │   k8s-rooster (Talos K8s + ArgoCD)            │
   │                                                │
   │  ┌────────────────────────────────────────┐    │
   │  │       AgentGateway (Enterprise)        │    │
   │  │                                        │    │
   │  │  LLM Gateway (port 8080/31572)         │    │
   │  │  ├─ /anthropic/* → Anthropic (Claude)  │    │
   │  │  ├─ /openai/* → OpenAI (GPT)           │    │
   │  │  └─ No auth required (AG holds keys)   │    │
   │  │                                        │    │
   │  │  MCP Gateway (port 8090/30168)         │    │
   │  │  ├─ /mcp-github → GitHub Copilot MCP   │    │
   │  │  │   JWT auth (Strict) + scope RBAC    │    │
   │  │  └─ /mcp → Everything (demo, no auth)  │    │
   │  │                                        │    │
   │  │  Policies: PII | Injection | Cred Leak │    │
   │  │  Tracing: → Langfuse + ClickHouse      │    │
   │  └────────────────────────────────────────┘    │
   └────────────────────────────────────────────────┘

   ┌────────────────────────────────────────────────┐
   │                    Okta                         │
   │  Org: integrator-7147223.okta.com               │
   │  Issuer: https://.../oauth2/default             │
   │                                                  │
   │  App: devops-copilot-service (client_credentials)│
   │  Scopes: mcp:read, mcp:write, mcp:admin         │
   └──────────────────────────────────────────────────┘
```

## Request Flow

### 1. User Invokes Agent

```
User/App → AWS IAM (invoke-agent-runtime) → AgentCore Runtime → POST /invocations → Agent
```

AWS IAM controls who can invoke the agent. Standard AWS access management.

### 2. Agent Gets Okta Token

```
Agent → Okta (client_credentials grant) → JWT with mcp:read, mcp:write scopes
```

The agent authenticates as a service account. Token is cached with a 5-minute expiry buffer.

### 3. Agent Discovers GitHub Tools

```
Agent + JWT → MCP Gateway (ngrok) → AgentGateway → GitHub Copilot MCP
  POST /mcp-github → initialize (JWT validated) → tools/list → GitHub tools
```

AgentGateway validates the JWT, checks scopes, and returns the filtered tool list.

### 4. Agent Calls LLM

```
Agent → LLM Gateway (ngrok) → AgentGateway → Anthropic API
  POST /anthropic/v1/chat/completions
    (no auth needed — AgentGateway injects API key)
    (PII redaction + prompt injection guard applied)
```

### 5. Agent Executes Tool Calls

```
LLM response: tool_calls: [{name: "create_issue", arguments: {...}}]
  → Agent routes to /mcp-github (from discovery map)
  → MCP tools/call + JWT → AgentGateway validates → GitHub MCP → GitHub API
  → Result fed back to LLM
```

### 6. Final Response

```
Agent → AgentCore → User/App
```

## Auth Model

Two layers of access control:

| Layer | What | How |
|-------|------|-----|
| **AWS IAM** | Who can invoke the agent | `bedrock-agentcore:InvokeAgentRuntime` permission |
| **AgentGateway + Okta** | What the agent can do | JWT validation + scope-based RBAC on MCP routes |

**LLM calls:** No auth needed — AgentGateway holds provider API keys as K8s Secrets.

**MCP calls:** Okta JWT required — `EnterpriseAgentgatewayPolicy` validates tokens in Strict mode.

## Infrastructure Components

### Terraform-Managed (AWS + Okta)

| Resource | Description |
|----------|-------------|
| `aws_ecr_repository.agent` | Container image repository |
| `aws_iam_role.agentcore_runtime` | Runtime role (ECR pull, Bedrock, logs) |
| `null_resource.agent_runtime` | Agent container runtime (arm64) |
| `null_resource.agent_runtime_endpoint` | Invocation endpoint |
| `okta_app_oauth.agentcore_service` | Service app (client_credentials) |
| `okta_auth_server_scope.mcp_*` | MCP scopes (read, write, admin) |

### k8s-rooster (ArgoCD-Managed)

| Component | Description |
|-----------|-------------|
| AgentGateway Proxy | LLM gateway (port 8080/31572) |
| MCP Gateway Proxy | MCP gateway (port 8090/30168) |
| Everything MCP Backend (header auth: X-AgentGateway-Auth) | GitHub Copilot MCP (api.githubcopilot.com) + PAT auth |
| Enterprise JWT Policy | Okta JWT validation on GitHub MCP route |
| RBAC Policies | Scope-based tool access (read/write/admin via CEL) |
| Destructive Block | Always-deny for delete/destroy operations |
| Security Policies | PII, prompt injection, credential leak protection |
| Langfuse OTel Collector | Trace fan-out to Langfuse + ClickHouse |

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| **No AgentCore Gateway** | AgentGateway handles all auth — portable across clouds |
| **client_credentials grant** | Agent authenticates as service account, simpler than OBO |
| **Okta issuer = oauth2/default** | Canonical issuer in JWT is `oauth2/default`, not the server ID |
| **GitHub-only MCP** | Focused demo — creates issues on ProfessorSeb/ai-kagent-demo |
| **MCP session IDs** | Required for stateful MCP protocol after initialize |
| **SSE response parsing** | AgentGateway returns MCP responses as Server-Sent Events |
| **arm64 images only** | AgentCore runtime requirement |
| **update-agent-runtime replaces env vars** | Must include `--environment-variables` on every update |

## Tracing & Observability

Every request through AgentGateway is traced via OpenTelemetry:

```
Agent → AgentGateway → OTel Collector (fan-out)
                           ├──► Langfuse — LLM analytics (tokens, cost, prompts)
                           └──► ClickHouse — Gateway metrics (routes, policies, rates)
```

All traces include `jwt.sub` for identity attribution.
