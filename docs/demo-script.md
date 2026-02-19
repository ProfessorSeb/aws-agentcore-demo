# Demo Script: Securing AI Agents with AgentGateway + AWS AgentCore

**Format:** Lightboard + Screen Share | **Target Length:** 12–15 min
**Presenter:** Seb | **Audience:** Platform engineers, security teams
**Repo:** [ProfessorSeb/aws-agentcore-demo](https://github.com/ProfessorSeb/aws-agentcore-demo)

**Drawing Colors:** 🔴 Red — Problems | 🔵 Blue — Solution | 🟢 Green — Security

---

## Part 1: The Problem (2 min) — 🎨 LIGHTBOARD

### What to Draw

1. Center: **"AI Agent"** box
2. Arrows RIGHT to **"Anthropic"** and **"OpenAI"** (LLMs)
3. Arrows LEFT to **"GitHub"** (MCP tools)
4. Mark up in 🔴 RED: ❌ API keys in code, ❌ No visibility, ❌ No PII filtering, ❌ No rate limits, ❌ No audit trail

### Script

> So here's how most teams build AI agents today. Agent needs to talk to LLMs — Claude, GPT. Needs to call tools — GitHub to create issues, manage repos.
>
> Every one of these arrows is ungoverned. API keys hardcoded. PII goes straight to the LLM. No rate limits — hope you don't hit a $50K bill. No audit trail for compliance.
>
> This is microservices circa 2016. We solved this for APIs with API gateways. Now we need to solve it for agents.

---

## Part 2: The Solution (2 min) — 🎨 LIGHTBOARD

### What to Draw

1. 🔴 X through all direct arrows
2. 🔵 Box in middle: **"AgentGateway"** — split: **"LLM Proxy"** | **"MCP Gateway"**
3. New 🔵 arrows: Agent → AgentGateway → LLMs/Tools
4. Labels: **"Policies | Tracing | Rate Limits | Auth"**
5. Badge: **"CNCF Open Source"**

### Script

> AgentGateway sits between your agents and everything they talk to. LLMs on one side, tools on the other.
>
> NOT Envoy with plugins. Purpose-built for agent traffic — understands LLM protocols, speaks MCP natively.
>
> One control plane for security, observability, rate limiting, authentication. And it's CNCF open source.
>
> Now here's the key insight — you don't need your cloud provider's gateway on top of this. AgentGateway IS your gateway. Your cloud provides compute, AgentGateway provides governance.

---

## Part 3: The Architecture (3 min) — 🎨 LIGHTBOARD

### What to Draw

1. **Top:** 🔵 AWS AgentCore — **"Agent Runtime"** (arm64 container)
2. **Left:** 🟢 Okta — **"client_credentials → JWT"**
3. Arrow: Agent → Okta → JWT with MCP scopes
4. **Middle:** Dashed lines for **ngrok tunnel**
5. **Bottom:** 🔵 **"k8s-rooster"** with AgentGateway inside
6. Inside AG: LLM side → Anthropic; MCP side → GitHub (with 🟢 JWT auth shield)
7. Trace lines to **Langfuse** + **ClickHouse**

### Script

> Full architecture. AgentCore up top — managed compute. Our DevOps Copilot runs as an arm64 container.
>
> The agent authenticates to Okta using client credentials — gets a JWT with MCP scopes. Simple machine-to-machine auth.
>
> ngrok tunnels connect AWS to our Kubernetes cluster — k8s-rooster.
>
> AgentGateway handles everything. LLM calls go through the proxy — it injects API keys, applies PII redaction, guards against injection. The agent never touches an API key.
>
> GitHub MCP calls go through with the JWT. AgentGateway validates the token, checks scopes, enforces RBAC. No valid token? No tools.
>
> No AWS-specific gateway in the chain. Same AgentGateway config works if you move to GCP, Azure, or bare metal tomorrow.

---

## Part 4: The Auth Flow (2 min) — 🎨 LIGHTBOARD

### What to Draw

```
① Invoker → AWS IAM        "invoke-agent-runtime"
② Agent → Okta             "client_credentials"
③ Okta → Agent             "JWT (mcp:read, mcp:write)"
④ Agent+JWT → AgentGateway "Bearer token on MCP calls"
⑤ AgentGateway validates   "JWKS ✓  Issuer ✓  Audience ✓  Scopes ✓"
⑥ AgentGW → GitHub MCP     "Tool call executed"
```

### Script

> Two layers of auth. AWS IAM controls who can invoke the agent. Standard stuff.
>
> Then the agent gets its own Okta JWT — client credentials grant, requesting mcp:read and mcp:write scopes.
>
> Every MCP call includes that JWT. AgentGateway validates signature, issuer, audience, expiration, then checks scopes against the tool being called.
>
> `mcp:read` lets you list issues. `mcp:write` lets you create them. Destructive ops like delete? Always blocked, regardless of scope.
>
> LLM calls don't need auth — AgentGateway holds the API keys. Simple.

---

## Part 5: Live Demo (4–5 min) — 💻 SCREEN SHARE

### 5.1 — Show the Agent Code (~30s)

```bash
cat agent/agent.py | grep -A5 "get_okta_token\|MCP_ENDPOINTS\|SYSTEM_PROMPT"
```

> The agent is straightforward. It gets an Okta token, discovers GitHub MCP tools, calls Claude for reasoning, executes tool calls. Default repo: ProfessorSeb/ai-kagent-demo.

### 5.2 — Get a Token from Okta (~30s)

```bash
curl -s -X POST \
  "https://integrator-7147223.okta.com/oauth2/default/v1/token" \
  -d "grant_type=client_credentials&scope=mcp:read mcp:write" \
  -u "$(terraform output -raw okta_service_client_id):$(terraform output -raw okta_service_client_secret)" \
  | jq .
```

> Standard OAuth2 client credentials. Look at the scopes — mcp:read, mcp:write. These control tool access.

### 5.3 — Invoke the Agent (~1.5 min)

```bash
PAYLOAD=$(echo -n '{"input":"Create a GitHub issue on ProfessorSeb/ai-kagent-demo titled Test Issue with a description of what this demo does"}' | base64 -w0)

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --content-type "application/json" \
  --payload "$PAYLOAD" \
  response.json

cat response.json | python3 -m json.tool
```

> Let's invoke the agent. We're asking it to create a GitHub issue.
>
> *(wait for response)*
>
> Issue created. The agent discovered GitHub tools through AgentGateway, called Claude for reasoning, then created the issue via MCP — all authenticated with Okta JWT.

### 5.4 — Show the MCP Gateway Logs (~30s)

```bash
kubectl logs -n agentgateway-system deploy/mcp-gateway-proxy --tail=10
```

> Look at the logs. See `jwt.sub=0oa104zvbj26VVleo698`? That's the Okta identity. Every MCP call is authenticated and attributed. Your compliance team can trace exactly who did what.

### 5.5 — Show Unauthenticated Rejection (~30s)

```bash
curl -s -X POST http://172.16.10.168:30168/mcp-github \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","clientInfo":{"name":"test","version":"0.1"},"capabilities":{}}}'
```

> Without a JWT? 401. No bearer token found. AgentGateway blocks it before it ever reaches GitHub.

### 5.6 — Show AgentGateway Policies (~30s)

```bash
kubectl get agentgatewaypolicies,enterpriseagentgatewaypolicies -n agentgateway-system
```

> All declarative YAML, managed by GitOps. JWT auth, RBAC, destructive op blocking, PII protection. No code changes needed.

---

## Part 6: Wrap Up (1 min)

> Five takeaways:
>
> **One** — No vendor-specific gateway. AgentGateway handles all auth and governance. Portable across clouds.
>
> **Two** — The agent holds minimal secrets. LLM keys and tool credentials stay in the gateway.
>
> **Three** — Scopes control tool access. Least privilege, enforced by AgentGateway.
>
> **Four** — Policies are YAML, managed by GitOps. Security team defines rules, developers don't change code.
>
> **Five** — Full audit trail. Every call traced with identity to Langfuse and ClickHouse.

### Call to Action

> Demo repo: **github.com/ProfessorSeb/aws-agentcore-demo**
> AgentGateway: **github.com/agentgateway/agentgateway**
> k8s-rooster: **github.com/ProfessorSeb/k8s-rooster**

---

## Timing Summary

| Section | Format | Duration |
|---------|--------|----------|
| Part 1: The Problem | Lightboard | ~2 min |
| Part 2: The Solution | Lightboard | ~2 min |
| Part 3: Architecture | Lightboard | ~3 min |
| Part 4: Auth Flow | Lightboard | ~2 min |
| Part 5: Live Demo | Screen Share | ~4–5 min |
| Part 6: Wrap Up | Talking Head | ~1 min |
| **Total** | | **~14–15 min** |

## Pre-Recording Checklist

- [ ] Okta token endpoint accessible (test `curl` beforehand)
- [ ] AgentCore runtime is warm (invoke once before recording)
- [ ] Langfuse has recent traces
- [ ] `kubectl` context set to maniak-rooster-jacob
- [ ] ngrok tunnels up and stable
- [ ] Anthropic API key valid (check LLM proxy)
- [ ] GitHub PAT valid (check MCP init on /mcp-github)
- [ ] Terminal font 16pt+, screen 1920×1080
