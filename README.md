# AWS AgentCore + Solo AgentGateway Demo — Knowledge Transfer Guide

## What This Repo Is

This is a working reference architecture that demonstrates how to build **governed AI agents** using AWS Bedrock AgentCore for compute, Solo AgentGateway for governance (LLM proxy + MCP gateway), and Okta for identity. The agent is a "DevOps Copilot" that can interact with GitHub via MCP tools, with every request authenticated and authorized through JWT tokens and scope-based RBAC.

The key design decision: **AWS provides compute, AgentGateway provides governance, Okta provides identity.** There is no AWS AgentCore Gateway in use — AgentGateway replaces it entirely, making the auth layer portable across cloud providers.

---

## Architecture Overview

```
                        Infra Network
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌──────────────────────────┐                                                │
│  │  AWS AgentCore            │                                               │
│  │  ┌──────────────────────┐ │     mTLS + API Key    ┌──────────────────┐   │
│  │  │ Agent Hosting Runtime │ │ ────────────────────► │ AgentGateway     │   │
│  │  │                      │ │                        │ LLM Gateway      │   │
│  │  │  ┌───────┐           │ │                        │                  │──►│ LLM
│  │  │  │ Agent │           │ │                        └──────────────────┘   │ (Anthropic,
│  │  │  └───────┘           │ │                         IAM / API Key        │  OpenAI, etc.)
│  │  │                      │ │                                               │
│  │  │                      │ │     AUTH Mechanism     ┌──────────────────┐   │
│  │  │                      │ │ ────────────────────► │ AgentGateway     │   │
│  │  └──────────────────────┘ │                        │ MCP Gateway      │   │
│  └────────────┬──────────────┘                        │                  │──►│ Tools
│               │                                       └────────┬─────────┘   │ (MCP Servers,
│               │ Token                                          │ AUTH         │  REST APIs)
│               │ Request                                        │ Mechanism    │
│               │                                                │             │
│               ▼                                                │             │
│         ┌──────────┐        Token Validation                   │             │
│         │   JWT    │        (in case OAuth)                    │             │
│         └────┬─────┘                                           │             │
│              │                                                 │             │
│              ▼                                                 │             │
│         ┌──────────┐ ◄────────────────────────────────────────┘             │
│         │   OKTA   │                                                        │
│         └──────────┘                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### How the Components Map

| Architecture Block | This Repo's Implementation | Where It Lives |
|---|---|---|
| **Agent Hosting Runtime** | AWS Bedrock AgentCore Runtime + Endpoint | AWS (managed) |
| **Agent** | `agent/agent.py` — Python/FastAPI container on ECR | AgentCore container |
| **AgentGateway LLM Gateway** | Solo AgentGateway LLM proxy (OpenAI-compatible) | k8s-rooster (on-prem k8s) |
| **AgentGateway MCP Gateway** | Solo AgentGateway MCP proxy with JWT auth + RBAC | k8s-rooster (on-prem k8s) |
| **LLM** | Anthropic Claude (via `claude-sonnet-4-20250514`) | External API |
| **Tools / MCP Servers** | GitHub MCP Server (issue/PR/repo management) | k8s-rooster |
| **Okta** | Okta OAuth2 Authorization Server | Okta Cloud |
| **JWT** | Okta-issued JWT with custom `mcp:read`, `mcp:write`, `mcp:admin` scopes | Token |
| **AUTH Mechanism (Agent → LLM GW)** | No auth needed — AgentGateway holds and injects LLM API keys | Config |
| **AUTH Mechanism (Agent → MCP GW)** | Okta JWT via `client_credentials` grant (or OBO token exchange) | Bearer token |
| **AUTH Mechanism (MCP GW → Tools)** | AgentGateway injects backend JWT from K8s Secret | SecretRef |

---

## Repository Structure

```
aws-agentcore-demo/
├── agent/                          # The AI agent that runs on AgentCore
│   ├── agent.py                    # Main agent code (FastAPI, LLM + MCP integration)
│   ├── Dockerfile                  # Container image for ECR/AgentCore
│   ├── requirements.txt            # Python deps (httpx, fastapi, uvicorn)
│   └── README.md                   # Agent-specific local dev instructions
│
├── terraform/                      # Infrastructure as Code
│   ├── main.tf                     # AWS provider, backend, locals
│   ├── variables.tf                # All configurable variables
│   ├── terraform.tfvars.example    # Example variable values (copy to .tfvars)
│   ├── iam.tf                      # IAM role for AgentCore runtime
│   ├── agentcore.tf                # ECR repo + AgentCore runtime + endpoint
│   ├── okta.tf                     # Okta apps, scopes, policies (Terraform-managed)
│   ├── gateway.tf                  # REMOVED — comment explaining why
│   ├── credentials.tf              # REMOVED — comment explaining why
│   ├── outputs.tf                  # ECR URL, IAM ARN, Okta endpoints
│   └── versions.tf                 # Provider version constraints
│
├── k8s/                            # Kubernetes manifests for AgentGateway
│   └── agentgateway-auth-policy.yaml  # JWT auth + scope RBAC + deny list
│
├── scripts/                        # Operational scripts
│   ├── deploy.sh                   # Full deploy: terraform → docker build → push → apply
│   ├── destroy.sh                  # Tear down everything
│   ├── test.sh                     # Check resource status (runtime, endpoint)
│   └── invoke-as-user.py           # PKCE login → OBO token exchange → agent invoke
│
├── docs/                           # Documentation & presentations
│   ├── architecture.md             # High-level architecture summary
│   ├── auth-flow-deep-dive.md      # Detailed auth chain walkthrough
│   ├── blog-why-agent-gateway.md   # Blog post explaining the "why"
│   ├── demo-guide.md               # Step-by-step terminal demo (5 min)
│   ├── demo-script.md              # Condensed talk track for live demos
│   └── agentgateway-governance-deck.pptx  # Presentation slides
│
└── README.md                       # This file
```

---

## How the Auth Chain Works (End-to-End)

This is the most important thing to understand. Every request flows through multiple auth boundaries.

### Step 1: Invoker → AgentCore (AWS IAM)

A user or system calls the AgentCore runtime endpoint using AWS IAM (SigV4 signed requests). This is standard AWS access control — whoever invokes the agent must have the right IAM permissions.

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --content-type "application/json" \
  --payload "$PAYLOAD_B64" response.json
```

The IAM role for the runtime is defined in `terraform/iam.tf` and allows `bedrock-agentcore.amazonaws.com` to assume it.

### Step 2: AgentCore → Agent Container (POST /invocations)

AgentCore forwards the request to the agent's `/invocations` endpoint. The agent is a FastAPI app running on port 8080 inside the container.

### Step 3: Agent → Okta (client_credentials Grant)

The agent needs a JWT to authenticate with AgentGateway's MCP gateway. It uses Okta's `client_credentials` grant — a machine-to-machine flow where the agent presents its client ID and secret to get a JWT.

The token contains custom scopes (`mcp:read`, `mcp:write`) that control what tools the agent can access. Tokens are cached with a 5-minute buffer before expiry.

```python
resp = await http_client.post(
    OKTA_TOKEN_URL,
    data={"grant_type": "client_credentials", "scope": "mcp:read mcp:write"},
    auth=(OKTA_CLIENT_ID, OKTA_CLIENT_SECRET),
)
```

The resulting JWT looks like:
```json
{
  "iss": "https://integrator-7147223.okta.com/oauth2/default",
  "aud": "api://default",
  "sub": "0oa104zvbj26VVleo698",
  "scp": ["mcp:read", "mcp:write"],
  "exp": 1739544600
}
```

### Step 4: Agent → AgentGateway LLM Proxy (No Auth)

LLM calls go to AgentGateway's OpenAI-compatible endpoint at `/anthropic/v1/chat/completions`. No authentication is required from the agent — AgentGateway holds the LLM provider API keys as Kubernetes Secrets and injects them into upstream requests.

AgentGateway also applies security policies on LLM traffic: PII redaction, prompt injection detection, and credential leak prevention.

### Step 5: Agent → AgentGateway MCP Gateway (Bearer JWT)

MCP tool calls include the Okta JWT as a Bearer token. AgentGateway validates the JWT against Okta's JWKS endpoint, then enforces scope-based RBAC using CEL expressions defined in `k8s/agentgateway-auth-policy.yaml`.

Three layers of access control:

**Layer 1 — JWT Validation:** Checks signature (RS256), issuer, audience, and expiration. No valid token = `401 Unauthorized`.

**Layer 2 — Scope-Based RBAC:** CEL expressions match JWT scopes to tool name prefixes.

| Scope | Can Access | Cannot Access |
|---|---|---|
| `mcp:read` | `list_*`, `get_*`, `search_*`, `read_*` | `create_*`, `post_*`, `update_*` |
| `mcp:write` | Everything in read + `create_*`, `post_*`, `send_*`, `update_*`, `comment_*` | `delete_*`, `merge_*` |
| `mcp:admin` | All tools | Destructive ops (always blocked) |

This filtering happens at two levels: `tools/list` responses hide unauthorized tools so the LLM never even sees them, and `tools/call` requests are rejected if scopes don't match.

**Layer 3 — Destructive Operation Deny List:** Regardless of scope, operations containing `delete`, `merge_pull_request`, or `destroy` in the tool name are always blocked.

### Step 6: AgentGateway → MCP Server (Backend JWT)

AgentGateway injects a backend JWT (stored as a Kubernetes Secret) into requests to the upstream MCP server. This is configured via `secretRef` in the AgentGateway config (managed on k8s-rooster, not in this repo).

### Step 7: Response Flows Back

The MCP tool result goes back through AgentGateway to the agent. The agent may feed it to the LLM for another iteration (tool use loop), or return the final response through AgentCore back to the invoker.

---

## On-Behalf-Of (OBO) Flow

In addition to the service identity flow above, the agent supports RFC 8693 Token Exchange for preserving user identity.

When a user invokes the agent with their own access token (via the `user_token` field or `X-User-Token` header), the agent exchanges that token with Okta to get a delegated JWT that carries the user's identity (`sub`, `email`, `groups`) but is scoped for the agent's downstream calls. AgentGateway then sees WHO the user is, enabling per-user RBAC.

The OBO flow is demonstrated by `scripts/invoke-as-user.py`, which opens a browser for Okta PKCE login, gets the user's token, and passes it to the agent.

If the OBO exchange fails, the agent falls back to `client_credentials` (service identity).

---

## Terraform: What Gets Created

Running `terraform apply` in the `terraform/` directory creates:

**AWS Resources:**
- ECR repository for the agent container image
- IAM role with permissions for ECR pull, CloudWatch Logs, and Bedrock invoke
- AgentCore Runtime (via AWS CLI `null_resource` — no native TF resource yet)
- AgentCore Runtime Endpoint

**Okta Resources:**
- OAuth2 service app (`client_credentials` for the agent)
- OAuth2 native/PKCE app (for user-facing OBO flow)
- Custom scopes: `mcp:read`, `mcp:write`, `mcp:admin`
- Auth server policy allowing both apps to request MCP scopes
- Policy rule with 60-minute token lifetime

**Not Created by Terraform:**
- AgentGateway deployment (managed via ArgoCD on k8s-rooster)
- MCP server deployment (managed via ArgoCD on k8s-rooster)
- ngrok tunnels (connectivity between AWS and k8s-rooster)

### Notes on the Terraform

The AgentCore runtime and endpoint are created via `null_resource` with `local-exec` provisioners because there is no native Terraform provider for Bedrock AgentCore yet. This means:

- Runtime/endpoint IDs are stored in local `.txt` files (`runtime_id.txt`, `endpoint_id.txt`)
- The provisioners include wait loops that poll for `READY` status (up to 30 attempts, 10s apart)
- Destroy provisioners clean up the resources
- The AgentCore runtime name must use underscores (not hyphens) — handled by `local.name_prefix_safe`

The `gateway.tf` and `credentials.tf` files are intentionally empty with comments explaining that AgentCore Gateway was removed in favor of AgentGateway.

---

## The Agent Code (agent/agent.py)

The agent is a single-file FastAPI application (~400 lines) that implements:

**Okta Token Management:** `get_okta_token()` for service identity and `exchange_token_obo()` for user delegation. Both cache tokens with a 5-minute buffer.

**LLM Integration:** `call_llm()` sends messages to AgentGateway's OpenAI-compatible endpoint. No auth needed. The agent uses Claude Sonnet as the default model.

**MCP Tool Integration:** `discover_mcp_tools()` performs the MCP protocol handshake (initialize → notifications/initialized → tools/list) and handles SSE response parsing. `call_mcp_tool()` makes individual tool calls. Both include Okta JWT Bearer tokens.

**Agent Loop:** `agent_loop()` ties it all together — discovers tools, sends user input + tool schemas to the LLM, executes any tool calls the LLM requests, feeds results back, and repeats up to 5 iterations until the LLM produces a final text response.

**Tool Routing:** Tools are discovered from configurable MCP endpoints (currently `/mcp-github`). A `TOOL_ROUTE_MAP` maps tool names to their MCP endpoint path so the agent knows where to send each tool call.

**SSE Parsing:** AgentGateway may return responses as Server-Sent Events (`data: {...}`) or plain JSON. The `_parse_sse_or_json()` helper handles both formats.

### Key Environment Variables for the Agent

| Variable | Purpose | Default |
|---|---|---|
| `LLM_GATEWAY_URL` | AgentGateway LLM proxy endpoint | `https://llm-agentgateway.ngrok.app` |
| `MCP_GATEWAY_URL` | AgentGateway MCP proxy endpoint | `https://mcp-agentgateway.ngrok.app` |
| `LLM_MODEL` | LLM model to use | `claude-sonnet-4-20250514` |
| `OKTA_TOKEN_URL` | Okta token endpoint | (empty — must be set) |
| `OKTA_CLIENT_ID` | Okta service app client ID | (empty — must be set) |
| `OKTA_CLIENT_SECRET` | Okta service app client secret | (empty — must be set) |
| `OKTA_SCOPES` | Scopes to request | `mcp:read mcp:write` |

---

## Deployment Steps

### Prerequisites

- AWS CLI with a configured profile (default: `agentcore-demo`)
- Docker (for building the agent image)
- Terraform >= 1.0
- An Okta developer org with API token
- k8s-rooster cluster running AgentGateway (separate from this repo)
- ngrok for tunneling between AWS and k8s-rooster

### Step-by-Step

1. **Configure variables:**
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your Okta org, API token, etc.
   ```

2. **Deploy everything:**
   ```bash
   ./scripts/deploy.sh
   ```
   This runs: terraform init → terraform apply (ECR + IAM first) → docker build + push → terraform apply (full).

3. **Verify:**
   ```bash
   ./scripts/test.sh
   ```
   Checks runtime and endpoint status.

4. **Test service auth:**
   ```bash
   aws bedrock-agentcore invoke-agent-runtime \
     --profile agentcore-demo \
     --agent-runtime-arn "$RUNTIME_ARN" \
     --content-type "application/json" \
     --payload "$(echo -n '{"input":"List available tools"}' | base64)" \
     response.json
   cat response.json | jq
   ```

5. **Test OBO auth:**
   ```bash
   export OKTA_CLIENT_ID_USER=$(cd terraform && terraform output -raw okta_client_id)
   python scripts/invoke-as-user.py "What tools can I use?"
   ```

### Teardown

```bash
./scripts/destroy.sh
```

---

## What Lives Outside This Repo

The following components are deployed separately on the k8s-rooster cluster (managed via ArgoCD):

- **AgentGateway (Enterprise):** The LLM proxy and MCP gateway binary. Configured with listeners for LLM and MCP traffic.
- **AgentGateway Auth Policy:** The `EnterpriseAgentgatewayPolicy` CRD from `k8s/agentgateway-auth-policy.yaml` is applied to k8s-rooster. It is stored in this repo for reference but deployed separately.
- **MCP Servers:** GitHub MCP server (and any other tool servers) run as pods on k8s-rooster.
- **LLM API Keys:** Stored as Kubernetes Secrets, injected by AgentGateway into upstream LLM requests.
- **Backend MCP JWT:** Stored as a Kubernetes Secret (`agentgateway-mcp-secret`), injected by AgentGateway into upstream MCP requests.
- **ngrok Tunnels:** Provide HTTPS connectivity between AgentCore (AWS) and AgentGateway (k8s-rooster). In production, replace with VPC peering or PrivateLink.

---

## Security Model Summary

| Boundary | Mechanism | What It Protects |
|---|---|---|
| Invoker → AgentCore | AWS IAM (SigV4) | Who can invoke the agent |
| Agent → Okta | client_credentials / OBO exchange | Agent/user identity |
| Agent → AgentGateway LLM | None (AG holds API keys) | LLM API keys never in agent code |
| Agent → AgentGateway MCP | Bearer JWT (Okta) | Which tools the agent can discover and call |
| AgentGateway → MCP Server | Backend JWT (K8s Secret) | MCP server access credentials |
| LLM traffic | PII redaction, injection guard, leak check | Data leaving the network |
| Destructive ops | Deny list (CEL expressions) | delete, merge, destroy always blocked |

**Key invariant:** The agent container holds ONLY Okta client credentials. No LLM API keys, no GitHub PATs, no MCP backend secrets.

---

## Documentation Index

| Document | Audience | What It Covers |
|---|---|---|
| `docs/architecture.md` | Engineers | Quick architecture summary with deploy commands |
| `docs/auth-flow-deep-dive.md` | Security / Architects | Detailed token flow, RBAC rules, verification commands |
| `docs/blog-why-agent-gateway.md` | Decision makers / Blog readers | "Why" narrative — governance gap, vendor lock-in, AgentGateway value prop |
| `docs/demo-guide.md` | Demo presenters | 5-minute terminal walkthrough with expected outputs |
| `docs/demo-script.md` | Demo presenters | Condensed talk track for live presentations |
| `docs/agentgateway-governance-deck.pptx` | Presentations | Slide deck |
