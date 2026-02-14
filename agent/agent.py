"""
DevOps Copilot Agent — AWS Bedrock AgentCore demo agent.

Architecture:
  AgentCore Runtime → This Agent → AgentGateway (LLM + MCP)
                                       ↓              ↓
                                   Anthropic      Slack/GitHub/MCP
                                       ↑              ↑
                                     Okta JWT auth on both paths

The agent uses AgentGateway as both:
1. LLM proxy (OpenAI-compatible) → /anthropic/v1/chat/completions
2. MCP tool gateway → /mcp/slack, /mcp-github, /mcp
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="DevOps Copilot Agent", version="0.2.0")

# --- Configuration via environment ---
AGENT_NAME = os.getenv("AGENT_NAME", "DevOps Copilot")

# AgentGateway endpoints (set via Terraform / env vars)
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "https://llm-agentgateway.ngrok.app")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "https://mcp-agentgateway.ngrok.app")

# LLM config
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# System prompt
SYSTEM_PROMPT = """You are a DevOps Copilot agent. You help with infrastructure management,
deployment pipelines, monitoring, and troubleshooting.

You have access to MCP tools via AgentGateway:
- Slack tools: post messages, read channels, manage conversations
- GitHub tools: manage issues, PRs, repositories
- General MCP tools: various utilities

When a user asks you to do something, use the appropriate tools.
Be concise and actionable in your responses."""

# HTTP client with connection pooling
http_client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)


# =============================================================================
# LLM Gateway Integration
# =============================================================================

async def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    """Call LLM via AgentGateway's OpenAI-compatible endpoint."""
    url = f"{LLM_GATEWAY_URL}/anthropic/v1/chat/completions"

    payload: dict[str, Any] = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": LLM_MAX_TOKENS,
    }
    if tools:
        payload["tools"] = tools

    logger.info("Calling LLM gateway: %s (model=%s, msgs=%d)", url, LLM_MODEL, len(messages))

    headers = {
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "devops-copilot-agent/0.2.0",
    }

    try:
        resp = await http_client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        logger.info("LLM response: tokens=%s", result.get("usage", {}))
        return result
    except httpx.HTTPStatusError as e:
        logger.error("LLM gateway error %d: %s", e.response.status_code, e.response.text[:500])
        raise
    except Exception as e:
        logger.error("LLM gateway connection error: %s", e)
        raise


# =============================================================================
# MCP Tool Integration
# =============================================================================

async def discover_mcp_tools(path: str = "/mcp") -> list[dict]:
    """Discover available tools from an MCP endpoint via AgentGateway."""
    url = f"{MCP_GATEWAY_URL}{path}"

    try:
        # MCP tool discovery — POST with initialize/tools_list
        resp = await http_client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "devops-copilot", "version": "0.2.0"},
                "capabilities": {},
            }},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                     "ngrok-skip-browser-warning": "true", "User-Agent": "devops-copilot-agent/0.2.0"},
        )
        logger.info("MCP init response (%s): %d", path, resp.status_code)

        # List tools
        resp = await http_client.post(
            url,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                     "ngrok-skip-browser-warning": "true", "User-Agent": "devops-copilot-agent/0.2.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            tools = data.get("result", {}).get("tools", [])
            logger.info("Discovered %d tools from %s", len(tools), path)
            return tools
    except Exception as e:
        logger.warning("MCP discovery failed for %s: %s", path, e)

    return []


async def call_mcp_tool(path: str, tool_name: str, arguments: dict) -> Any:
    """Call an MCP tool via AgentGateway."""
    url = f"{MCP_GATEWAY_URL}{path}"

    try:
        resp = await http_client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": tool_name,
                "arguments": arguments,
            }},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                     "ngrok-skip-browser-warning": "true", "User-Agent": "devops-copilot-agent/0.2.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", data)
        logger.info("MCP tool %s result: %s", tool_name, str(result)[:200])
        return result
    except Exception as e:
        logger.error("MCP tool call failed (%s/%s): %s", path, tool_name, e)
        return {"error": str(e)}


def mcp_tools_to_openai_format(mcp_tools: list[dict]) -> list[dict]:
    """Convert MCP tool schemas to OpenAI function calling format."""
    openai_tools = []
    for tool in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


# =============================================================================
# Tool routing — maps tool names to MCP paths
# =============================================================================

# Built dynamically during tool discovery
TOOL_ROUTE_MAP: dict[str, str] = {}

MCP_ENDPOINTS = {
    "/mcp": "Everything MCP server",
    "/mcp/slack": "Slack MCP tools",
    "/mcp-github": "GitHub MCP tools",
}


async def discover_all_tools() -> list[dict]:
    """Discover tools from all MCP endpoints and build routing map."""
    all_tools = []
    TOOL_ROUTE_MAP.clear()

    for path, desc in MCP_ENDPOINTS.items():
        tools = await discover_mcp_tools(path)
        for tool in tools:
            TOOL_ROUTE_MAP[tool["name"]] = path
        all_tools.extend(tools)
        logger.info("Discovered %d tools from %s (%s)", len(tools), path, desc)

    logger.info("Total tools discovered: %d", len(all_tools))
    return all_tools


# =============================================================================
# Agent Loop — LLM + Tool Use
# =============================================================================

async def agent_loop(user_input: str, session_id: str) -> str:
    """
    Main agent loop:
    1. Discover MCP tools
    2. Send user message + tools to LLM
    3. If LLM wants to call a tool → call it via MCP → feed result back
    4. Repeat until LLM gives a final text response
    """
    # Discover available tools
    mcp_tools = await discover_all_tools()
    openai_tools = mcp_tools_to_openai_format(mcp_tools)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    max_iterations = 5
    for i in range(max_iterations):
        logger.info("Agent loop iteration %d/%d", i + 1, max_iterations)

        # Call LLM with tools
        result = await call_llm(messages, tools=openai_tools if openai_tools else None)

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        # If LLM wants to call tools
        if finish_reason == "tool_calls" or message.get("tool_calls"):
            # Add assistant message to history
            messages.append(message)

            tool_calls = message.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                tool_args = json.loads(func.get("arguments", "{}"))

                logger.info("Tool call: %s(%s)", tool_name, json.dumps(tool_args)[:200])

                # Route to correct MCP endpoint
                mcp_path = TOOL_ROUTE_MAP.get(tool_name, "/mcp")
                tool_result = await call_mcp_tool(mcp_path, tool_name, tool_args)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(tool_result, default=str),
                })

            continue  # Loop back to LLM with tool results

        # Final text response
        return message.get("content", "I couldn't generate a response.")

    return "I reached the maximum number of tool call iterations. Please try a simpler request."


# =============================================================================
# FastAPI Endpoints
# =============================================================================

@app.get("/health")
async def health():
    """Health check endpoint for AgentCore."""
    return {
        "status": "healthy",
        "agent": AGENT_NAME,
        "version": "0.2.0",
        "llm_gateway": LLM_GATEWAY_URL,
        "mcp_gateway": MCP_GATEWAY_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/invoke")
@app.post("/invocations")
async def invoke(request: Request):
    """
    Main invocation endpoint for AgentCore runtime.
    AgentCore calls /invocations, but we also keep /invoke for direct testing.
    """
    body = await request.json()
    logger.info("Received invocation: %s", json.dumps(body, default=str)[:500])

    user_input = body.get("input", body.get("message", body.get("prompt", "")))
    session_id = body.get("sessionId", "unknown")

    try:
        response_text = await agent_loop(user_input, session_id)
    except Exception as e:
        logger.exception("Agent loop failed")
        response_text = f"Error: {e}"

    return JSONResponse(content={
        "output": response_text,
        "sessionId": session_id,
        "agent": AGENT_NAME,
        "version": "0.2.0",
    })


@app.get("/tools")
async def list_tools():
    """List all discovered MCP tools and their routes."""
    tools = await discover_all_tools()
    return {
        "tools": [
            {
                "name": t.get("name"),
                "description": t.get("description", "")[:100],
                "mcp_path": TOOL_ROUTE_MAP.get(t.get("name", ""), "unknown"),
            }
            for t in tools
        ],
        "total": len(tools),
        "mcp_endpoints": MCP_ENDPOINTS,
    }


@app.get("/")
async def root():
    """Root endpoint with agent info."""
    return {
        "agent": AGENT_NAME,
        "version": "0.2.0",
        "description": "DevOps Copilot — uses AgentGateway for LLM + MCP tools with Okta auth",
        "config": {
            "llm_gateway": LLM_GATEWAY_URL,
            "mcp_gateway": MCP_GATEWAY_URL,
            "model": LLM_MODEL,
        },
        "endpoints": {
            "health": "GET /health",
            "invoke": "POST /invoke",
            "tools": "GET /tools",
        },
    }


@app.post("/{path:path}")
async def catch_all_post(path: str, request: Request):
    """Catch-all POST handler to discover what AgentCore sends."""
    body = await request.body()
    headers = dict(request.headers)
    logger.info("CATCH-ALL POST /%s | Headers: %s | Body: %s", path, json.dumps(headers)[:500], body.decode()[:500])

    # Try to handle as an invoke request
    try:
        data = json.loads(body)
        user_input = data.get("input", data.get("message", data.get("prompt", str(data))))
        response_text = await agent_loop(user_input, "catch-all")
        return JSONResponse(content={"output": response_text})
    except Exception as e:
        logger.error("Catch-all handler error: %s", e)
        return JSONResponse(content={"output": f"Received at /{path}", "error": str(e)})


@app.api_route("/{path:path}", methods=["GET", "PUT", "PATCH", "DELETE"])
async def catch_all_other(path: str, request: Request):
    """Catch-all for non-POST methods."""
    logger.info("CATCH-ALL %s /%s", request.method, path)
    return JSONResponse(content={"path": path, "method": request.method})


@app.on_event("shutdown")
async def shutdown():
    await http_client.aclose()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting %s on port %d", AGENT_NAME, port)
    logger.info("LLM Gateway: %s", LLM_GATEWAY_URL)
    logger.info("MCP Gateway: %s", MCP_GATEWAY_URL)
    uvicorn.run(app, host="0.0.0.0", port=port)
