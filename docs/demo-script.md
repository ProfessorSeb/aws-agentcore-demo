# Demo Script: Securing AI Agents with AgentGateway + AWS AgentCore

**Format:** Lightboard + Screen Share | **Target Length:** 12–15 min
**Presenter:** Seb | **Audience:** Platform engineers, security teams (enterprise/banking)
**Repo:** [ProfessorSeb/aws-agentcore-demo](https://github.com/ProfessorSeb/aws-agentcore-demo)

**Drawing Colors:**
- 🔴 **Red** — Problems, anti-patterns, X marks
- 🔵 **Blue** — Solution components, AgentGateway, architecture
- 🟢 **Green** — Security checkpoints, auth, policies

---

## Part 1: The Problem (2 min) — 🎨 LIGHTBOARD

### What to Draw

1. Draw a box in the center: **"AI Agent"**
2. Draw arrows going RIGHT to **"Anthropic"** and **"OpenAI"** (LLM providers)
3. Draw arrows going LEFT to **"Slack"** and **"GitHub"** (MCP tools)
4. Now mark up the problems in 🔴 RED:
   - ❌ next to agent box: **"API keys in agent code"**
   - ❌ above the LLM arrows: **"No visibility"**
   - ❌ on the LLM arrow: **"No PII filtering"**
   - ❌ below: **"No rate limits"**
   - ❌ bottom: **"No audit trail"**

### Script

> So here's how most teams build AI agents today. You've got your agent — maybe it's a DevOps copilot, a support bot, whatever — and it needs to talk to LLMs. Claude, GPT, you name it.
>
> *(draw the LLM arrows)*
>
> And it needs to call tools. Slack to post messages, GitHub to create PRs.
>
> *(draw the tool arrows)*
>
> Now here's the problem. Every one of these arrows is ungoverned.
>
> *(start marking red X's)*
>
> API keys? Hardcoded in the agent or sitting in environment variables. PII filtering? Doesn't exist — your customer's social security number goes straight to the LLM provider. Rate limits? Hope you don't hit a $50K bill on a Saturday. Audit trail? Good luck explaining to your compliance team which user triggered which call.
>
> If this looks familiar, it should. This is microservices circa 2016 — before API gateways, before service mesh. Every team reinventing auth, retries, logging. We solved this problem for APIs. Now we need to solve it for agents.

---

## Part 2: The Solution — AgentGateway (2 min) — 🎨 LIGHTBOARD

### What to Draw

1. Cross out all the direct arrows with a big 🔴 RED **X**
2. Draw a 🔵 BLUE box in the middle: **"AgentGateway"**
3. Split it into two halves: **"LLM Proxy"** (left) | **"MCP Gateway"** (right)
4. New arrows in 🔵 BLUE: Agent → AgentGateway → LLMs
5. New arrows in 🔵 BLUE: Agent → AgentGateway → Tools
6. Label the gateway box: **"Policies | Tracing | Rate Limits | Auth"**
7. Below the gateway, draw **"Langfuse"** and **"ClickHouse"** with trace arrows
8. Add a badge: **"CNCF Open Source"**

### Script

> So what's the fix? You put something in the middle.
>
> *(draw AgentGateway box)*
>
> This is AgentGateway. It sits between your agents and everything they talk to — LLMs on one side, tools on the other.
>
> *(draw the new arrows)*
>
> Now, this is NOT Envoy with some plugins bolted on. AgentGateway is purpose-built for agent traffic. It understands LLM protocols natively — token counting, streaming, model routing. And it speaks MCP — the Model Context Protocol — so it can govern tool calls too.
>
> *(label the gateway)*
>
> One control plane for security policies, observability, rate limiting, and authentication. All your agents, all your LLMs, all your tools — governed.
>
> *(draw Langfuse + ClickHouse)*
>
> Every call gets traced. Langfuse for LLM-specific analytics — token costs, latency, model performance. ClickHouse for gateway-level metrics. Full picture.
>
> And it's CNCF open source. No vendor lock-in.

---

## Part 3: The Architecture (3 min) — 🎨 LIGHTBOARD

### What to Draw (build incrementally as you narrate)

1. **Top:** 🔵 AWS AgentCore box — write **"Agent Runtime"** inside, **"arm64 container"** below it
2. **Left:** 🟢 Okta box — **"OAuth2 / OIDC"**
3. Arrow: **User** → Okta → **JWT token** (green arrow)
4. Arrow: User + JWT → **AgentCore Gateway** → writes **"Validates JWT"** (green checkmark)
5. **Middle:** Dashed lines for **ngrok tunnel** — label **"Secure Tunnel"**
6. **Bottom:** 🔵 Big box: **"k8s-rooster"** (Kubernetes cluster) — AgentGateway inside it
7. Inside AgentGateway left side: arrows to **Anthropic**, **OpenAI**, **xAI**
8. Inside AgentGateway right side: arrows to **Slack**, **GitHub**, **Tools**
9. 🟢 Shield icons on the gateway: **"PII"**, **"Injection Guard"**, **"Credential Leak"**
10. Trace lines down to **Langfuse** + **ClickHouse**

### Script

> Let me show you the full architecture for what we've built.
>
> *(draw AgentCore box)*
>
> Up top, we've got AWS Bedrock AgentCore. This is where the agent actually runs — it's a managed runtime. Our DevOps Copilot agent runs as an arm64 container. AgentCore handles scaling, lifecycle, all that.
>
> *(draw Okta)*
>
> Over here — Okta. Our identity provider. Users authenticate here and get a JWT with specific MCP scopes.
>
> *(draw auth arrows)*
>
> User hits Okta, gets a JWT. That JWT goes to the AgentCore Gateway, which validates it — checks the signature against Okta's JWKS endpoint, verifies the issuer, audience, expiration. Invalid token? You're done. You never reach the agent.
>
> *(draw ngrok tunnel)*
>
> Now here's the cool part. The agent runs in AWS, but AgentGateway runs on our own Kubernetes cluster — k8s-rooster. We use ngrok to create a secure tunnel between them.
>
> *(draw k8s-rooster with AgentGateway)*
>
> Inside k8s-rooster, AgentGateway handles everything. LLM calls go through the proxy — it injects the API key so the agent never sees it, applies PII redaction, guards against prompt injection.
>
> *(draw tool arrows)*
>
> MCP tool calls go through the gateway too. And here's what makes this enterprise-grade — On-Behalf-Of token exchange. When the agent posts to Slack, it posts AS the user. Not a service account. Jane asks the agent to post to Slack, the message shows up from Jane.
>
> *(draw policy shields)*
>
> PII protection, prompt injection detection, credential leak prevention — all running as gateway policies.
>
> *(draw traces)*
>
> And everything — every LLM call, every tool invocation — traced to Langfuse and ClickHouse. You know exactly who did what, when, and how much it cost.

---

## Part 4: The Auth Flow (2 min) — 🎨 LIGHTBOARD

### What to Draw

Draw a numbered sequence flow (1–6) with 🟢 GREEN arrows:

```
① User → Okta         "Auth Code + PKCE"
② Okta → User         "JWT"
③ User+JWT → Gateway   "Bearer token"
④ Gateway validates    "JWKS ✓  Issuer ✓  Audience ✓  Exp ✓"
⑤ Agent → AgentGW     "OBO token exchange"
⑥ AgentGW → Tools     "Execute AS the user"
```

Next to step ②, write the decoded JWT claims:

```
iss: okta
aud: api://default
sub: jane.doe@bank.com
scp: [mcp:read, mcp:write]
exp: 1hr
```

### Script

> Let's zoom into the auth flow because this is what your security team cares about.
>
> *(draw step 1)*
>
> Step one — user authenticates with Okta using Auth Code plus PKCE. Standard OAuth2, nothing exotic.
>
> *(draw step 2, write JWT claims)*
>
> Okta issues a JWT. And look at these claims — issuer is Okta, audience matches our gateway config, subject is the actual human user, and scopes control what they can do. `mcp:read` lets you list Slack channels. `mcp:write` lets you post messages. Least privilege.
>
> *(draw steps 3-4)*
>
> That JWT goes as a Bearer token to the AgentCore Gateway, which validates everything — signature via JWKS, issuer, audience, expiration. Four checks before you even reach the agent.
>
> *(draw steps 5-6)*
>
> Now the agent needs to call tools. It does an On-Behalf-Of token exchange with AgentGateway, and the gateway executes the tool call AS the user.
>
> Every hop is authenticated. Zero trust, end to end. The agent never holds credentials — if it's compromised, there's nothing to steal. And for compliance? Every single call is traced back to a specific human user. Your auditors will love you.

---

## Part 5: Live Demo (4–5 min) — 💻 SCREEN SHARE

### Transition

> Alright, enough drawing. Let me show you this actually working. I'm going to switch over to my terminal.

*(Switch from lightboard to screen share. Have terminal open with large font.)*

---

### 5.1 — Show the Okta Config (~30s)

```bash
cd aws-agentcore-demo/terraform
cat okta.tf
```

> First, let's look at how Okta is configured. This is all Terraform — infrastructure as code.
>
> You can see we've got two OAuth apps — one for the user-facing auth flow, one for service-to-service. And here are our custom scopes: `mcp:read` and `mcp:write`. These map directly to what tools the agent can call on behalf of the user.

---

### 5.2 — Get a Token from Okta (~30s)

```bash
curl -s -X POST \
  "https://integrator-7147223.okta.com/oauth2/aus104zseyg64swj3698/v1/token" \
  -d "grant_type=client_credentials&scope=mcp:read mcp:write" \
  -u "$(terraform output -raw okta_service_client_id):$(terraform output -raw okta_service_client_secret)" \
  | python3 -m json.tool
```

> Let's grab a token. Standard OAuth2 client credentials flow, requesting our MCP scopes.
>
> *(wait for response)*
>
> There it is — access token, token type bearer, expires in 3600 seconds. Let's decode it.

---

### 5.3 — Decode the JWT (~30s)

```bash
echo "$TOKEN" | cut -d'.' -f2 | base64 -d | python3 -m json.tool
```

> See the claims? Issuer is our Okta org. Audience matches the gateway configuration. And there are our scopes — `mcp:read`, `mcp:write`. This is what controls tool access.

---

### 5.4 — Show the AgentCore Gateway Config (~30s)

```bash
cat gateway.tf
```

> Now look at how AgentCore validates this token. CUSTOM_JWT authorizer, pointing at Okta's discovery URL. AgentCore fetches the JWKS keys automatically and validates every incoming request. No custom code — just config.

---

### 5.5 — Invoke the Agent (~1 min)

```bash
export RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:103739863673:runtime/devops_copilot_runtime-k6izWBE3YT"
PAYLOAD=$(echo -n '{"input": "List all Slack channels and post hello to #general"}' | base64 -w0)

aws bedrock-agentcore invoke-agent-runtime \
  --region us-east-1 \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --content-type "application/json" \
  --payload "$PAYLOAD" \
  response.json

cat response.json | python3 -m json.tool
```

> Now the fun part. Let's invoke the agent. We're asking it to list Slack channels and post a message to #general.
>
> *(wait for response)*
>
> Look at what happened. The agent discovered the available MCP tools through AgentGateway, called Claude for reasoning — also through AgentGateway — figured out it needed the Slack tools, and posted to #general. All governed. The agent never touched an API key. The Slack message shows up from the authenticated user, not a bot account.

---

### 5.6 — Show Langfuse Traces (~1 min)

*(Open browser to Langfuse dashboard)*

> Let me show you what that looked like from the observability side.
>
> *(click into the latest trace)*
>
> Here's the trace waterfall. You can see the full lifecycle — user request comes in, LLM call to Claude, tool discovery via MCP, tool execution for Slack, and the response back. Every step has the user identity attached. You can see token costs, which model was used, latency for each hop. This is the audit trail your compliance team needs.

---

### 5.7 — Show AgentGateway Policies (~30s)

```bash
kubectl get agentgatewaypolicies -n agentgateway-system
```

> Last thing — the security policies. These are Kubernetes custom resources, managed by GitOps.
>
> PII protection — redacts sensitive data before it hits the LLM provider. Prompt injection guard — detects and blocks injection attempts. Credential leak protection — makes sure API keys don't leak in responses. All declarative YAML, all version controlled. No code changes needed.

---

## Part 6: Wrap Up (1 min) — 🗣️ TALKING HEAD / LIGHTBOARD

### Transition

> Let me switch back and recap what we just saw.

### Script

> Five things to take away from this:
>
> **One** — the agent has zero secrets. No API keys, no credentials. The gateway holds everything.
>
> **Two** — every single call is traced to a human user. Full audit trail, from request to tool execution.
>
> **Three** — scopes control tool access. Least privilege, enforced at the identity layer.
>
> **Four** — policies are YAML, managed by GitOps. Your security team defines the rules, developers don't need to change code.
>
> **Five** — this is the same governance pattern that API gateways brought to microservices a decade ago. We're bringing it to AI agents.

### Call to Action

> Everything I showed you is open source and the full demo is on GitHub.
>
> The demo repo — **github.com/ProfessorSeb/aws-agentcore-demo** — has the Terraform, the agent code, all the configs.
>
> AgentGateway itself — **github.com/agentgateway/agentgateway** — CNCF open source project.
>
> And the Kubernetes cluster — **github.com/ProfessorSeb/k8s-rooster**.
>
> If you're building AI agents at your org and you need governance, check it out. Drop me a comment, I'll see you in the next one.

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

- [ ] Lightboard markers: 🔴 red, 🔵 blue, 🟢 green, white for labels
- [ ] Terminal font size bumped up (16pt+)
- [ ] Okta token endpoint accessible (test `curl` beforehand)
- [ ] AgentCore runtime is warm (cold starts can add 30s+ — invoke once before recording)
- [ ] Langfuse has recent traces to show (run a test invocation 5 min before)
- [ ] `kubectl` context set to k8s-rooster
- [ ] ngrok tunnel is up and stable
- [ ] Browser tab with Langfuse dashboard open and logged in
- [ ] Screen share resolution set (1920×1080, no scaling weirdness)
