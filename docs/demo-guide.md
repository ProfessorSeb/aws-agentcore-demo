# Demo Guide: Terminal/CLI Test Flow (5 mins)

## Prereqs
```bash
export AWS_PROFILE=agentcore-demo  # SSO profile
pip install httpx  # For curls
cd aws-agentcore-demo
terraform output  # Note endpoints/client IDs
```

## 1. Service Auth (AgentCore CLI ~30s)
```bash
aws agent-runtime invoke-endpoint \
  --endpoint-id devops_copilot_endpoint \
  --input '{"invocations": [{"messages": [{"role": "user", "content": "List safe tools and what I can do"}]}]}' | jq
```
**Expect:** `auth_mode: "service"`, read-only tools list (RBAC)

## 2. OBO User Auth (PKCE CLI ~1min)
```bash
python scripts/invoke-as-user.py "Show available tools – what can I write?"
```
**Expect:** Browser Okta login → `auth_mode: "OBO"`, same RBAC tools (user identity)

## 3. Public Proxy Tests (Gateway + Backend JWT ~1min)
```bash
# Tools list (gateway JWT injected)
curl -s https://mcp-agentgateway.ngrok.app/mcp-everything/tools/list \
  -H 'Accept: text/event-stream' \
  -d '{}' | jq '.tools | length'  # 50+

# RBAC block (destructive tool)
curl -s -X POST https://mcp-agentgateway.ngrok.app/mcp-everything/tools/call \
  -H 'Accept: text/event-stream' \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"delete_issue","arguments":{}}}' | grep -i forbidden  # 403

# Backend auth fail (no header from gateway)
curl -s https://mcp-server-everything.internal/mcp/tools/list -d '{}'  # 401 (if enforced)
```

## 4. Logs/Tracing (~30s)
```bash
# Gateway logs
kubectl logs -n agentgateway-system -l app.kubernetes.io/name=agentgateway --tail=20 | grep mcp-everything

# Tracing (Langfuse)
open https://langfuse.com/p/<project>/traces?search=mcp-everything
```
**Expect:** JWT validated, scopes checked, tool RBAC logs.

## 5. Deploy/Update (~2min)
```bash
# Agent update
docker build -t agent .
docker tag agent:latest 103739863673.dkr.ecr.us-east-1.amazonaws.com/devops-copilot-agent:latest
docker push ...

# Runtime refresh
terraform apply  # --environment-variables new MCP URL

# Rotate backend JWT
kubectl create secret generic agentgateway-mcp-secret --from-literal=Authorization="Bearer $(gog okta token)" -n agentgateway-system --dry-run=client -o yaml | kubectl apply -f -
```

**Pro tip:** Record `asciinema` or `warp` session for blog/GIFs.

**Full E2E demo in 5 mins!** Terminal-first. 🚀