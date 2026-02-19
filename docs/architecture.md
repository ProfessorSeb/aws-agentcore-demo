# Architecture: AWS AgentCore + AgentGateway + Okta (Everything MCP)

## The Big Picture

**AgentCore:** Managed compute (runtime/endpoint)
**AgentGateway:** Governance (JWT/RBAC/backend JWT)
**Okta:** Identity (service/OBO)
**Everything MCP:** Multi-tool backend (50+ tools)

No AgentCore Gateway. Portable auth.

## Diagram
```
User/App → AWS IAM → AgentCore Runtime → Agent Container
  ↓
Okta JWT (service/OBO)
  ↓
AgentGateway
  ├── LLM Proxy (keys hidden) → Anthropic/OpenAI
  └── MCP Proxy (/mcp-everything)
      ├── JWT Validate + Tool RBAC
      └── Backend JWT Injected → Everything MCP Server
```

## Flow
1. **Invoke:** IAM auth → runtime → /invocations
2. **JWT:** Agent gets Okta token (OBO exchange if user_token)
3. **Tools:** Discover /mcp-everything/tools/list (RBAC filtered)
4. **LLM:** Chat via proxy (no auth)
5. **Tools:** Call /mcp-everything/tools/call (RBAC + backend JWT)
6. **Response:** Final output

## Backend Auth (Gateway → MCP)
SecretRef JWT:
```
policies:
  auth:
    secretRef:
      name: agentgateway-mcp-secret
      key: Authorization
```
MCP validates (iss/aud/scope).

## Deploy
terraform apply  # AWS + Okta
ArgoCD sync k8s-rooster  # Gateway + MCP