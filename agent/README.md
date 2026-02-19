# DevOps Copilot Agent

Demo agent for AWS Bedrock AgentCore. Runs as a FastAPI container that connects to AgentGateway for LLM and MCP tool access, authenticated via Okta JWT.

## Local Development

```bash
pip install -r requirements.txt

# Set required env vars (get from terraform output)
export OKTA_TOKEN_URL="https://your-org.okta.com/oauth2/default/v1/token"
export OKTA_CLIENT_ID="your-service-client-id"
export OKTA_CLIENT_SECRET="your-service-client-secret"

python agent.py
# → http://localhost:8080
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Agent info |
| `/health` | GET | Health check (used by AgentCore) |
| `/invocations` | POST | Agent invocation (called by AgentCore runtime) |

## Docker

```bash
docker build -t devops-copilot-agent .
docker run -p 8080:8080 \
  -e OKTA_TOKEN_URL="..." \
  -e OKTA_CLIENT_ID="..." \
  -e OKTA_CLIENT_SECRET="..." \
  devops-copilot-agent
```

## Invoke Example

```bash
# Service auth (agent uses client_credentials to get Okta JWT)
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": "What tools can I use?"}'

# OBO auth (pass a user token for identity delegation)
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": "List open issues", "user_token": "<okta-user-access-token>"}'
```
