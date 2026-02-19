# AWS AgentCore + Solo AgentGateway Demo (Okta Auth)

[![Runtime Status](https://img.shields.io/badge/Runtime-v13%20READY-brightgreen)](https://us-east-1.console.aws.amazon2.aws.amazon.com/agent-runtime/home?region=us-east-1#/runtimes/devops_copilot_runtime-k6izWBE3YT)
[![Gateway](https://img.shields.io/badge/AgentGateway-v0.11.1--patch1-blue)](https://mcp-agentgateway.ngrok.app/mcp-everything/health)
[![Okta](https://img.shields.io/badge/Okta-Dual%20Auth-teal)](https://integrator-7147223.okta.com)

**Live Demo:** AgentCore → Agent (Okta service/OBO) → AgentGateway (JWT/RBAC + backend header auth) → Everything MCP (50+ tools)

## Okta Setup (Terraform-managed)
| App | Type | Client ID | Grant | Scopes |
|-----|------|-----------|-------|--------|
| **Service** | Service | `0oa104zvbj26VVleo698` | client_credentials + token_exchange | `mcp:read/write/admin` |
| **User (OBO)** | Native/PKCE | `0oa10acvbdkjhhrAJ698` | authorization_code | `openid profile mcp:*` |

- **Issuer:** `https://integrator-7147223.okta.com/oauth2/default`
- **Outputs:** `terraform output okta_authorize_url` (PKCE login)

## Quickstart (5 mins)
1. **AWS (service auth):**
   ```bash
   aws agent-runtime invoke-endpoint --profile agentcore-demo --endpoint-id devops_copilot_endpoint \
     --input '{"invocations": [{"messages": [{"role": "user", "content": "List safe tools"}]}]}' | jq
   ```
   → `auth_mode: "service"` + RBAC tools

2. **OBO (user login):**
   ```bash
   python scripts/invoke-as-user.py "Show tools"
   ```
   → Browser Okta PKCE → `auth_mode: "OBO"`

3. **Public Proxy (header auth):**
   ```bash
   curl https://mcp-agentgateway.ngrok.app/mcp-everything/tools/list \
     -H 'X-AgentGateway-Auth: demo-shared-secret-123' \
     -H 'Accept: text/event-stream' -d '{}' | jq '.tools | length'
   ```
   → 50+ tools (w/o header: 401)

## Features
- **Dual Okta Auth:** Service + OBO (RFC 8693 user delegation)
- **Gateway Governance:** JWT validate + Tool RBAC (read/write/block) + backend header auth
- **Backend:** Everything MCP (no PAT/vendor hassle)
- **Deck:** [v2.pptx](docs/agentgateway-governance-deck-v2.pptx)

## Deploy
```bash
cd terraform
terraform init && terraform apply  # AWS runtime + Okta apps
cd ../k8s-rooster  # ArgoCD syncs AgentGateway
```

**Live from repo!** terraform → runtime → ngrok gateway. Fork & run.