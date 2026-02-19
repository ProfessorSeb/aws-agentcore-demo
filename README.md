# AWS AgentCore + Solo AgentGateway Demo

[![Runtime Status](https://img.shields.io/badge/Runtime-v12%20READY-brightgreen)](https://us-east-1.console.aws.amazon2.aws.amazon.com/agent-runtime/home?region=us-east-1#/runtimes/devops_copilot_runtime-k6izWBE3YT)
[![Gateway](https://img.shields.io/badge/AgentGateway-v0.11.1--patch1-blue)](https://mcp-agentgateway.ngrok.app/mcp-everything/health)

**Live Demo:** AgentCore Runtime → Agent (dual Okta auth) → AgentGateway (JWT/RBAC) → Everything MCP (50+ tools)

## Quickstart (5 mins)
```bash
# AWS CLI (profile=agentcore-demo)
aws agent-runtime invoke-endpoint --endpoint-id devops_copilot_endpoint \
  --input '{"invocations": [{"messages": [{"role": "user", "content": \"List safe tools\"}]}]}'
```

**Public Proxy Test:**
```
curl https://mcp-agentgateway.ngrok.app/mcp-everything/tools/list \
  -H 'Accept: text/event-stream' -d '{}'
```

## Features
- **Dual Auth:** Service (client_creds) + OBO (RFC 8693)
- **Governance:** Okta JWT + Tool RBAC (read/write/block destructive)
- **Backend:** mcp-server-everything (no PAT hassle)
- **Deck:** [agentgateway-governance-deck.pptx](docs/agentgateway-governance-deck.pptx)

## Architecture
![Diagram](docs/architecture.png)  <!-- Add Mermaid? -->

terraform apply  # Deploys runtime/agent
k8s-rooster ArgoCD syncs gateway

## Okta OBO CLI
```bash
python scripts/invoke-as-user.py
```

**Live!** Repo → AWS runtime → ngrok gateway. Share away.