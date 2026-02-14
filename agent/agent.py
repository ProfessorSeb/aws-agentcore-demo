"""
DevOps Copilot Agent — A simple demo agent for AWS Bedrock AgentCore.

Exposes an HTTP endpoint that AgentCore can invoke. The agent:
- Receives requests from AgentCore runtime
- Processes them using a DevOps Copilot persona
- Can call tools via MCP through the AgentCore gateway
"""

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="DevOps Copilot Agent", version="0.1.0")

AGENT_NAME = os.getenv("AGENT_NAME", "DevOps Copilot")
AGENT_DESCRIPTION = (
    "I'm a DevOps Copilot that helps with infrastructure management, "
    "deployment pipelines, monitoring, and troubleshooting. "
    "I can interact with your infrastructure tools via MCP."
)


@app.get("/health")
async def health():
    """Health check endpoint for AgentCore."""
    return {"status": "healthy", "agent": AGENT_NAME, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/invoke")
async def invoke(request: Request):
    """
    Main invocation endpoint for AgentCore runtime.
    Receives agent invocation requests and returns responses.
    """
    body = await request.json()
    logger.info("Received invocation: %s", json.dumps(body, default=str)[:500])

    user_input = body.get("input", body.get("message", ""))
    session_id = body.get("sessionId", "unknown")

    # Simple response logic — in production, this would call an LLM
    # via the AgentCore gateway and use MCP tools
    response_text = process_request(user_input)

    return JSONResponse(content={
        "output": response_text,
        "sessionId": session_id,
        "agent": AGENT_NAME,
    })


@app.get("/")
async def root():
    """Root endpoint with agent info."""
    return {
        "agent": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "invoke": "/invoke (POST)",
        },
    }


def process_request(user_input: str) -> str:
    """Process a user request. Placeholder for LLM + MCP tool calls."""
    user_input_lower = user_input.lower().strip()

    if not user_input_lower:
        return f"Hello! I'm {AGENT_NAME}. {AGENT_DESCRIPTION}\n\nHow can I help you today?"

    if "help" in user_input_lower or "what can you do" in user_input_lower:
        return (
            f"I'm {AGENT_NAME}. Here's what I can help with:\n\n"
            "• **Infrastructure**: Check cluster status, node health, resource usage\n"
            "• **Deployments**: Review deployment status, rollback, scale\n"
            "• **Monitoring**: Query metrics, check alerts, review logs\n"
            "• **Troubleshooting**: Diagnose issues, suggest fixes\n\n"
            "In production, I connect to your tools via MCP through the AgentCore gateway."
        )

    if "status" in user_input_lower:
        return (
            "📊 **Infrastructure Status** (demo)\n\n"
            "• k8s-rooster cluster: ✅ Healthy (3 nodes)\n"
            "• AgentGateway: ✅ Running\n"
            "• MCP endpoints: ✅ Connected\n"
            "• Last deployment: 2h ago (all pods healthy)"
        )

    return (
        f"Got it! You asked: \"{user_input}\"\n\n"
        "In production, I'd route this through the AgentCore gateway to MCP tools "
        "on your k8s-rooster cluster. For now, this is a demo response.\n\n"
        "Try: 'help', 'status', or describe what you need."
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting %s on port %d", AGENT_NAME, port)
    uvicorn.run(app, host="0.0.0.0", port=port)
