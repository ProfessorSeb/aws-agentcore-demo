# DevOps Copilot Agent

Simple demo agent for AWS Bedrock AgentCore.

## Local Development

```bash
pip install -r requirements.txt
python agent.py
# → http://localhost:8080
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Agent info |
| `/health` | GET | Health check |
| `/invoke` | POST | Agent invocation |

## Docker

```bash
docker build -t devops-copilot-agent .
docker run -p 8080:8080 devops-copilot-agent
```

## Invoke Example

```bash
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{"input": "What can you do?", "sessionId": "test-123"}'
```
