# Why Your AI Agents Need a Gateway: Securing AWS AgentCore with AgentGateway

You wouldn't deploy microservices without an API gateway. So why are teams deploying AI agents with direct, ungoverned access to LLMs and external tools?

If you're running agents on AWS Bedrock AgentCore — or anywhere else — and those agents are calling Claude, GPT-4, or hitting MCP tool servers directly, you have a governance gap. No rate limiting. No audit trail. No PII filtering. No failover. Every team wiring up their own retry logic, their own auth handling, their own cost tracking. It's 2016 microservices all over again, except the blast radius includes sending your customer database to a third-party LLM.

[AgentGateway](https://github.com/agentgateway/agentgateway) fixes this. It's an open-source (CNCF) gateway purpose-built for AI agent traffic — both LLM calls and MCP tool calls — giving you a single control plane for everything your agents talk to.

This post walks through why you need it, how it works, and how the [aws-agentcore-demo](https://github.com/ProfessorSeb/aws-agentcore-demo) wires it all together.

## The Problem: Agents Without Guardrails

An AI agent is, at its core, a loop: receive input → call an LLM → maybe call some tools → return output. The interesting part is what happens in those calls.

When an agent on AgentCore calls Anthropic's API directly:

- **API keys live in the agent container.** Every developer who can deploy an agent has access to production LLM credentials.
- **No visibility.** What prompts are being sent? What data is in them? You don't know until something leaks.
- **No cost controls.** One runaway agent loop burns through your API budget in minutes. There's no per-user or per-agent rate limiting.
- **No failover.** Anthropic has an outage? Your agent is dead. Hope someone set up a retry with exponential backoff — oh wait, each team did it differently.
- **No security policies.** PII goes straight to the LLM. Prompt injection attempts pass through unfiltered. Credentials in responses get forwarded to users.

And then there's MCP. Your agent discovers tools — Slack, GitHub, internal APIs — via Model Context Protocol servers. Each MCP server needs auth. Each one is another surface to secure, another thing to monitor, another connection to manage.

Every team solving these problems independently is wasted engineering. Worse, most teams don't solve them at all.

## The Solution: AgentGateway

AgentGateway sits between your agents and everything they talk to. LLMs and MCP tool servers both route through it.

This isn't Envoy with some AI plugins bolted on. AgentGateway is a purpose-built proxy with its own xDS-inspired control plane, designed from the ground up for agent traffic patterns. It understands:

- **LLM protocols** — OpenAI-compatible chat completions, streaming, token counting
- **MCP protocol** — tool discovery, tool invocation, server lifecycle
- **Agent-specific policies** — PII redaction, prompt injection detection, per-user token budgets

Two logical functions, one binary:

1. **LLM Proxy** — OpenAI-compatible endpoint that routes to any provider (Anthropic, OpenAI, xAI, local models)
2. **MCP Gateway** — aggregates multiple MCP servers, presents a unified tool catalog to agents

Your agent code doesn't change. Point it at AgentGateway instead of the LLM provider directly. That's it.

## Traffic Flow: How This Demo Works

The [aws-agentcore-demo](https://github.com/ProfessorSeb/aws-agentcore-demo) is a working reference architecture. Here's what's actually running:

```
┌─────────────────────────┐
│   AWS Bedrock AgentCore  │
│  ┌─────────────────────┐ │
│  │ Agent Container      │ │
│  │ (arm64, Python/      │ │
│  │  FastAPI)            │ │
│  └────────┬─────────────┘ │
└───────────┼───────────────┘
            │ ngrok tunnels
            ▼
┌─────────────────────────────┐
│  k8s-rooster (on-prem k8s)  │
│                              │
│  ┌────────────────────────┐  │
│  │    AgentGateway         │  │
│  │  ┌──────┐ ┌──────────┐ │  │
│  │  │ LLM  │ │   MCP    │ │  │
│  │  │Proxy │ │ Gateway  │ │  │
│  │  └──┬───┘ └────┬─────┘ │  │
│  └─────┼──────────┼───────┘  │
└────────┼──────────┼──────────┘
         │          │
    ┌────▼───┐  ┌───▼────────┐
    │Anthropic│  │MCP Servers │
    │OpenAI   │  │- Slack     │
    │xAI      │  │- GitHub    │
    └─────────┘  │- Tools     │
                 └────────────┘
```

**The agent container** runs on AgentCore as an arm64 Python/FastAPI application. It doesn't hold any LLM API keys. It knows one endpoint: AgentGateway.

**LLM calls** go through AgentGateway's OpenAI-compatible proxy. The agent calls `/anthropic/v1/chat/completions` — AgentGateway routes it to Anthropic, applies policies, logs the interaction, and returns the response. Path-based routing means `/openai/v1/*` goes to OpenAI, `/anthropic/v1/*` goes to Anthropic, all on the same gateway.

**MCP tool calls** go through AgentGateway's MCP gateway. The agent discovers available tools (Slack messaging, GitHub operations, general utilities) through a single MCP endpoint. AgentGateway aggregates multiple upstream MCP servers into one catalog.

**Connectivity** between AWS and the on-prem [k8s-rooster](https://github.com/ProfessorSeb/k8s-rooster) cluster uses ngrok tunnels. This is the pragmatic bridge for a demo — in production, you'd use VPC peering, PrivateLink, or similar.

**Identity** flows through the entire chain. Okta provides OAuth2 tokens via an on-behalf-of flow. AgentGateway validates JWTs using OIDC discovery. When an MCP tool executes — say, posting a Slack message — it acts as the authenticated user, not a service account. The human's identity is preserved end-to-end.

**Infrastructure** is fully codified: Terraform manages AWS resources and Okta configuration, ArgoCD handles everything on k8s.

## Guardrails: The Real Value

The gateway pattern only matters if you can enforce policies at the gateway. Here's what AgentGateway gives you:

### Security Policies

**PII Protection.** Before a prompt reaches the LLM, AgentGateway scans for personally identifiable information and redacts it. Social security numbers, email addresses, phone numbers — stripped before they leave your network. Same on the response side.

**Prompt Injection Detection.** Agents process user input. Users (or attackers) submit malicious prompts designed to hijack the agent's behavior. AgentGateway detects common jailbreak patterns and blocks them before the LLM ever sees them.

**Credential Leak Prevention.** LLMs sometimes hallucinate or echo back credentials that appeared in training data or context. AgentGateway scans responses for patterns matching API keys, tokens, and passwords, blocking them before they reach users.

### Traffic Management

**Rate limiting** operates at two levels — requests and tokens:

```yaml
rate_limiting:
  - match:
      provider: xai
    limits:
      - requests_per_minute: 10
      - tokens_per_minute: 5000
```

Per-user limits prevent any single agent or user from monopolizing capacity. Token-level limits prevent cost blowouts even within request limits.

**Model failover** keeps agents running when providers have issues:

```yaml
failover:
  primary: anthropic/claude-sonnet-4-20250514
  fallback:
    - openai/gpt-4o
    - xai/grok-3
  trigger:
    - status_code: 529  # overloaded
    - status_code: 500
    - timeout_ms: 30000
```

If Anthropic returns a 529 (overloaded), the request automatically retries against OpenAI. Your agent doesn't know or care.

**Path-based routing** lets you expose multiple providers on a single gateway:

```
/anthropic/v1/* → Anthropic Claude
/openai/v1/*    → OpenAI GPT-4
/xai/v1/*       → xAI Grok
```

Agents pick their provider by URL path. The gateway handles auth, policies, and observability uniformly across all of them.

### Observability: Dual Export

This demo exports telemetry to two systems simultaneously using an OpenTelemetry Collector with fan-out:

**Langfuse** (via OTLP) gives you the LLM-focused view:
- Token usage and costs per request, per user, per agent
- Full prompt and completion logging
- Trace waterfalls showing the complete chain: user request → LLM call → tool call → tool response → LLM call → final response

**ClickHouse + Solo UI** gives you the infrastructure view:
- Gateway throughput and latency metrics
- Policy enforcement statistics (how many PII redactions? how many blocked injections?)
- Route analytics across providers

Every LLM call and every MCP tool invocation is traced end-to-end with correlated trace IDs. When something goes wrong, you can follow a single request from the user through the agent, through the gateway, to the LLM and tools, and back.

### Identity and Auth

The Okta integration deserves special attention. AgentGateway validates incoming JWTs via OIDC discovery — no hardcoded secrets, no manual key rotation. The on-behalf-of flow means:

1. User authenticates with Okta
2. Agent receives a delegated token
3. AgentGateway validates the token and passes identity context downstream
4. MCP tools execute with the user's permissions

This is how you prevent a support agent from accessing engineering tools, or an intern's agent from having admin-level Slack access. Identity-aware agent infrastructure.

## Why This Matters for Production

The parallel to API gateways in the microservices era is exact. In 2015, teams deployed services that called each other directly — no rate limiting, no circuit breaking, no centralized auth. Then API gateways and service meshes became standard infrastructure because you can't run production systems without governance.

AI agents are at that same inflection point. Today, most agent deployments are demos or internal tools where governance doesn't matter yet. But the moment you have multiple teams deploying agents, multiple LLM providers, user-facing agent interactions, or any compliance requirements, you need a control plane.

AgentGateway gives you:

- **One policy layer** for all agent traffic, LLM and tool calls alike
- **Declarative configuration** in YAML, managed via GitOps (ArgoCD in this demo)
- **Provider independence** — swap LLMs without touching agent code
- **Full audit trail** — every prompt, every response, every tool call, logged and traced
- **Cost governance** — per-user, per-agent, per-provider rate limits on both requests and tokens

## Try It

The full working demo is at [ProfessorSeb/aws-agentcore-demo](https://github.com/ProfessorSeb/aws-agentcore-demo). It includes Terraform for AWS and Okta provisioning, ArgoCD applications for the k8s side, and the agent container code.

The backing Kubernetes cluster configuration lives at [ProfessorSeb/k8s-rooster](https://github.com/ProfessorSeb/k8s-rooster).

AgentGateway itself is at [agentgateway/agentgateway](https://github.com/agentgateway/agentgateway) — CNCF open-source, Apache 2.0 licensed.

The agent infrastructure space is moving fast. AgentCore, MCP, and agent gateways are all weeks-to-months old. The teams that build governance into their agent platform now — rather than bolting it on after an incident — are the ones that'll actually get agents into production. Start with the gateway.
