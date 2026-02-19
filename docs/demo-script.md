# Live Demo Script: AgentCore + AgentGateway (5 mins)

**Audience:** PM/Eng/SE – show governance without lock-in.

**Prep:** AWS CLI (`agentcore-demo`), browser, terminal. Share ngrok/Langfuse.

## 1. The Stack (30s)
> Full stack: AgentCore compute → Okta JWT → AgentGateway (RBAC/JWT backend) → Everything MCP.

```
Runtime (terraform) → Agent (Python) → Gateway (/mcp-everything) → 50+ tools
```

## 2. Service Auth Invoke (30s)
```bash
aws agent-runtime invoke-endpoint --endpoint-id devops_copilot_endpoint \
  --input '{"invocations": [{"messages": [{"role": "user", "content": "List safe tools"}]}]}' | jq '.output | fromjson'
```
> `auth_mode: "service"` + read-only tools (RBAC!).

## 3. OBO User (1min)
```bash
python scripts/invoke-as-user.py "What tools can I use?"
```
> Browser Okta → OBO exchange → `auth_mode: "OBO"` (user scopes).

## 4. Proxy + Backend JWT (1min)
```bash
# Tools (gateway injects JWT)
curl https://mcp-agentgateway.ngrok.app/mcp-everything/tools/list -H 'Accept: text/event-stream' -d '{}' | jq '.tools | length'  # 50+

# RBAC block
curl -X POST https://mcp-agentgateway.ngrok.app/mcp-everything/tools/call \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"delete_issue","arguments":{}}}' | jq  # 403
```

## 5. Tracing (30s)
> Langfuse: End-to-end traces (JWT sub, tool calls, tokens).

```
kubectl logs -n agentgateway-system deploy/enterprise-agentgateway | grep JWT
```

## 6. Deploy (1min)
```bash
terraform apply  # Runtime refresh
# k8s-rooster ArgoCD auto-syncs
```

**Boom – governed agents w/o lock-in!** Q&A.

**Record:** asciinema demo-guide.md