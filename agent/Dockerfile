FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

EXPOSE 8080

ENV PORT=8080
ENV AGENT_NAME="DevOps Copilot"
ENV LLM_GATEWAY_URL="https://llm-agentgateway.ngrok.app"
ENV MCP_GATEWAY_URL="https://mcp-agentgateway.ngrok.app"
ENV LLM_MODEL="claude-sonnet-4-20250514"
ENV LLM_MAX_TOKENS="1024"
ENV OKTA_TOKEN_URL=""
ENV OKTA_CLIENT_ID=""
ENV OKTA_CLIENT_SECRET=""
ENV OKTA_SCOPES="mcp:read mcp:write"

CMD ["python", "agent.py"]
