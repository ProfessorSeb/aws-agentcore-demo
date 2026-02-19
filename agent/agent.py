"""
DevOps Copilot Agent — AWS Bedrock AgentCore demo agent.

Architecture:
  AgentCore Runtime → This Agent → AgentGateway (LLM + MCP)
                                       ↓              ↓
                                   Anthropic      GitHub MCP
                                                       ↑
                                                  Okta JWT auth

The agent uses AgentGateway as both:
1. LLM proxy (OpenAI-compatible) → /anthropic/v1/chat/completions
2. MCP tool gateway → /mcp-github

Auth model (dual mode):
- LLM calls: No auth needed — AgentGateway holds provider API keys
- MCP calls (service): Okta JWT via client_credentials — agent identity only
- MCP calls (OBO): Okta Token Exchange (RFC 8693) — retains user identity
  User token → agent exchanges for delegated token → AgentGateway sees user
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="DevOps Copilot Agent", version="0.4.0")

# --- Configuration via environment ---
AGENT_NAME = os.getenv("AGENT_NAME", "DevOps Copilot")

# AgentGateway endpoints (set via Terraform / env vars)
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "https://llm-agentgateway.ngrok.app")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "https://mcp-agentgateway.ngrok.app")

# LLM config
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# Okta config — agent authenticates to AgentGateway MCP via client_credentials
OKTA_TOKEN_URL = os.getenv("OKTA_TOKEN_URL", "")
OKTA_CLIENT_ID = os.getenv("OKTA_CLIENT_ID", "")
OKTA_CLIENT_SECRET = os.getenv("OKTA_CLIENT_SECRET", "")
OKTA_SCOPES = os.getenv("OKTA_SCOPES", "mcp:read mcp:write")

# System prompt
SYSTEM_PROMPT = """You are a DevOps Copilot agent. You help with infrastructure management,
deployment pipelines, monitoring, and troubleshooting.

You have access to GitHub MCP tools via AgentGateway:
- Create, list, and manage issues
- Create and manage pull requests
- Browse repositories, files, and code

Default repository: ProfessorSeb/ai-kagent-demo

When a user asks you to do something, use the appropriate GitHub tools.
Be concise and actionable in your responses."""

# HTTP client with connection pooling
http_client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)


# =============================================================================
# Okta Token Management
# =============================================================================

_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0}


async def get_okta_token() -> str:
    """Get a valid Okta access token via client_credentials, refreshing if expired.

    Used as the default (service identity) when no user token is provided.
    """
    # Return cached token if still valid (with 5-min buffer)
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 300:
        return _token_cache["access_token"]

    if not OKTA_TOKEN_URL or not OKTA_CLIENT_ID or not OKTA_CLIENT_SECRET:
        logger.warning("Okta credentials not configured — MCP calls will be unauthenticated")
        return ""

    logger.info("Refreshing Okta access token via client_credentials grant")

    try:
        resp = await http_client.post(
            OKTA_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "scope": OKTA_SCOPES,
            },
            auth=(OKTA_CLIENT_ID, OKTA_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = time.time() + expires_in

        logger.info("Okta token refreshed (expires in %ds)", expires_in)
        return access_token

    except Exception as e:
        logger.error("Failed to get Okta token: %s", e)
        return ""


# OBO token cache — keyed by user token hash to avoid leaking tokens in keys
_obo_token_cache: dict[str, dict[str, Any]] = {}


async def exchange_token_obo(user_token: str) -> str:
    """Exchange a user's access token for a delegated OBO token (RFC 8693).

    The agent presents the user's token to Okta and gets back a new token
    that carries the user's identity (sub, email, groups) but is scoped
    for the agent's downstream calls. AgentGateway sees WHO the user is.

    Flow: User token → Okta Token Exchange → Delegated JWT → AgentGateway
    """
    import hashlib
    cache_key = hashlib.sha256(user_token.encode()).hexdigest()[:16]

    # Check cache
    cached = _obo_token_cache.get(cache_key)
    if cached and time.time() < cached["expires_at"] - 300:
        logger.info("Using cached OBO token for user")
        return cached["access_token"]

    if not OKTA_TOKEN_URL or not OKTA_CLIENT_ID or not OKTA_CLIENT_SECRET:
        logger.warning("Okta credentials not configured — falling back to client_credentials")
        return await get_okta_token()

    logger.info("Exchanging user token for OBO token via RFC 8693 Token Exchange")

    try:
        resp = await http_client.post(
            OKTA_TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": user_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "scope": OKTA_SCOPES,
                "audience": "api://agentgateway",
            },
            auth=(OKTA_CLIENT_ID, OKTA_CLIENT_SECRET),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        _obo_token_cache[cache_key] = {
            "access_token": access_token,
            "expires_at": time.time() + expires_in,
        }

        logger.info("OBO token obtained (expires in %ds, token_type=%s)",
                     expires_in, data.get("issued_token_type", "unknown"))
        return access_token

    except httpx.HTTPStatusError as e:
        logger.error("OBO token exchange failed %d: %s", e.response.status_code, e.response.text[:500])
        logger.info("Falling back to client_credentials")
        return await get_okta_token()
    except Exception as e:
        logger.error("OBO token exchange error: %s", e)
        logger.info("Falling back to client_credentials")
        return await get_okta_token()


# =============================================================================
# LLM Gateway Integration
# =============================================================================

async def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict:
    """Call LLM via AgentGateway's OpenAI-compatible endpoint.

    No auth needed — AgentGateway holds provider API keys and injects them.
    """
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
        "User-Agent": "devops-copilot-agent/0.4.0",
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

async def _mcp_headers(user_token: str | None = None) -> dict[str, str]:
    """Build headers for MCP requests, including Okta JWT.

    If user_token is provided, uses OBO Token Exchange to get a delegated
    token that retains the user's identity. Otherwise falls back to
    client_credentials (service identity only).
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "devops-copilot-agent/0.4.0",
    }
    if user_token:
        token = await exchange_token_obo(user_token)
        logger.info("Using OBO token (user identity preserved)")
    else:
        token = await get_okta_token()
        logger.info("Using client_credentials token (service identity)")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# Session IDs per MCP endpoint — required for stateful MCP after initialize
MCP_SESSION_IDS: dict[str, str] = {}


async def discover_mcp_tools(path: str = "/mcp", user_token: str | None = None) -> list[dict]:
    """Discover available tools from an MCP endpoint via AgentGateway."""
    url = f"{MCP_GATEWAY_URL}{path}"
    headers = await _mcp_headers(user_token)

    try:
        # MCP tool discovery — POST with initialize, capture session ID
        resp = await http_client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "devops-copilot", "version": "0.4.0"},
                "capabilities": {},
            }},
            headers=headers,
        )
        logger.info("MCP init response (%s): %d", path, resp.status_code)

        # Capture session ID from response header
        session_id = resp.headers.get("mcp-session-id", "")
        if session_id:
            MCP_SESSION_IDS[path] = session_id
            logger.info("MCP session ID for %s: %s", path, session_id[:20])

        # Parse SSE response to get the JSON data
        init_data = _parse_sse_or_json(resp)

        # Send initialized notification (required by MCP protocol)
        notify_headers = {**headers}
        if session_id:
            notify_headers["Mcp-Session-Id"] = session_id
        await http_client.post(
            url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=notify_headers,
        )

        # List tools — must include session ID
        list_headers = {**headers}
        if session_id:
            list_headers["Mcp-Session-Id"] = session_id
        resp = await http_client.post(
            url,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=list_headers,
        )
        if resp.status_code == 200:
            data = _parse_sse_or_json(resp)
            tools = data.get("result", {}).get("tools", [])
            logger.info("Discovered %d tools from %s", len(tools), path)
            return tools
    except Exception as e:
        logger.warning("MCP discovery failed for %s: %s", path, e)

    return []


def _parse_sse_or_json(resp: httpx.Response) -> dict:
    """Parse response that may be SSE (data: ...) or plain JSON."""
    text = resp.text.strip()
    if text.startswith("data:"):
        # Extract JSON from SSE format
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


async def call_mcp_tool(path: str, tool_name: str, arguments: dict, user_token: str | None = None) -> Any:
    """Call an MCP tool via AgentGateway."""
    url = f"{MCP_GATEWAY_URL}{path}"
    headers = await _mcp_headers(user_token)

    # Include session ID if we have one for this endpoint
    session_id = MCP_SESSION_IDS.get(path, "")
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    try:
        resp = await http_client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": tool_name,
                "arguments": arguments,
            }},
            headers=headers,
        )
        resp.raise_for_status()
        data = _parse_sse_or_json(resp)
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
    "/mcp-github": "GitHub MCP tools",
}


async def discover_all_tools(user_token: str | None = None) -> list[dict]:
    """Discover tools from all MCP endpoints and build routing map."""
    all_tools = []
    TOOL_ROUTE_MAP.clear()

    for path, desc in MCP_ENDPOINTS.items():
        tools = await discover_mcp_tools(path, user_token)
        for tool in tools:
            TOOL_ROUTE_MAP[tool["name"]] = path
        all_tools.extend(tools)
        logger.info("Discovered %d tools from %s (%s)", len(tools), path, desc)

    logger.info("Total tools discovered: %d", len(all_tools))
    return all_tools


# =============================================================================
# Agent Loop — LLM + Tool Use
# =============================================================================

async def agent_loop(user_input: str, session_id: str, user_token: str | None = None) -> str:
    """
    Main agent loop:
    1. Discover MCP tools (authenticated via Okta JWT)
    2. Send user message + tools to LLM (no auth needed)
    3. If LLM wants to call a tool → call it via MCP → feed result back
    4. Repeat until LLM gives a final text response

    If user_token is provided, uses OBO Token Exchange so AgentGateway
    sees the user's identity. Otherwise uses client_credentials.
    """
    auth_mode = "OBO (user identity)" if user_token else "client_credentials (service identity)"
    logger.info("Agent loop starting — auth mode: %s", auth_mode)

    # Discover available tools
    mcp_tools = await discover_all_tools(user_token)
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
                tool_result = await call_mcp_tool(mcp_path, tool_name, tool_args, user_token)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
                })

            continue

        # Final text response
        content = message.get("content", "No response from LLM")
        logger.info("Agent loop complete after %d iterations", i + 1)
        return content

    return "Agent loop reached maximum iterations without a final response."


# =============================================================================
# FastAPI Endpoints
# =============================================================================

@app.get("/health")
async def health():
    """Health check for AgentCore runtime."""
    return {"status": "healthy", "agent": AGENT_NAME, "version": "0.4.0"}


@app.post("/invocations")
async def invoke(request: Request):
    """Main invocation endpoint for AgentCore.

    Supports two auth modes:
    1. Service identity (default): Agent uses client_credentials to get its own JWT
    2. On-Behalf-Of: If 'user_token' is in the payload, agent exchanges it via
       RFC 8693 Token Exchange to get a delegated JWT that preserves user identity.
       AgentGateway can then enforce per-user RBAC policies.
    """
    try:
        body = await request.json()
        user_input = body.get("input", body.get("prompt", ""))

        if not user_input:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing 'input' or 'prompt' in request body"},
            )

        # Extract user token if provided (enables OBO flow)
        user_token = body.get("user_token", None)
        # Also check Authorization header (for direct HTTP callers)
        if not user_token:
            auth_header = request.headers.get("X-User-Token", "")
            if auth_header:
                user_token = auth_header

        session_id = body.get("session_id", f"session-{datetime.now(timezone.utc).isoformat()}")
        auth_mode = "OBO" if user_token else "service"
        logger.info("Invocation received: session=%s auth=%s input=%s",
                     session_id, auth_mode, user_input[:100])

        response = await agent_loop(user_input, session_id, user_token)

        return JSONResponse(content={
            "output": response,
            "session_id": session_id,
            "agent": AGENT_NAME,
            "auth_mode": auth_mode,
        })

    except Exception as e:
        logger.exception("Invocation failed")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )


@app.get("/")
async def root():
    return {"agent": AGENT_NAME, "version": "0.4.0", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
