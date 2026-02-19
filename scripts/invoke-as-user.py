#!/usr/bin/env python3
"""
Invoke the DevOps Copilot agent as an authenticated user (OBO flow).

This script:
1. Opens a browser for Okta login (Authorization Code + PKCE)
2. Gets the user's access token
3. Passes it to the agent via AgentCore invoke
4. The agent exchanges it for an OBO token (RFC 8693)
5. AgentGateway sees the user's identity in the JWT

Usage:
    python scripts/invoke-as-user.py "List open issues on ProfessorSeb/ai-kagent-demo"
    python scripts/invoke-as-user.py --service "List open issues"   # fallback to client_credentials

Environment:
    OKTA_ISSUER          - e.g. https://integrator-7147223.okta.com/oauth2/default
    OKTA_CLIENT_ID_USER  - The native/PKCE app client ID (NOT the service app)
    AWS_PROFILE          - AWS profile for AgentCore invoke (default: agentcore-demo)
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

# Okta config
OKTA_ISSUER = os.getenv("OKTA_ISSUER", "https://integrator-7147223.okta.com/oauth2/default")
OKTA_CLIENT_ID = os.getenv("OKTA_CLIENT_ID_USER", "")
CALLBACK_PORT = 8888
CALLBACK_URL = f"http://localhost:{CALLBACK_PORT}/callback"

# AWS config
AWS_PROFILE = os.getenv("AWS_PROFILE", "agentcore-demo")
RUNTIME_ARN = os.getenv("RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:us-east-1:103739863673:runtime/devops_copilot_runtime-k6izWBE3YT")


def pkce_pair():
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def get_user_token():
    """Run the PKCE authorization code flow to get a user access token."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)

    # Build authorize URL
    params = urllib.parse.urlencode({
        "client_id": OKTA_CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email mcp:read mcp:write",
        "redirect_uri": CALLBACK_URL,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    authorize_url = f"{OKTA_ISSUER}/v1/authorize?{params}"

    # Start local callback server
    auth_code = [None]
    server_error = [None]

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("state", [None])[0] != state:
                server_error[0] = "State mismatch"
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Close this tab.")
                return
            if "error" in qs:
                server_error[0] = qs["error"][0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Error: {qs['error'][0]}".encode())
                return
            auth_code[0] = qs.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authenticated!</h2>"
                             b"<p>You can close this tab and return to the terminal.</p>"
                             b"</body></html>")

        def log_message(self, format, *args):
            pass  # Suppress server logs

    server = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"\n🔐 Opening browser for Okta login...")
    print(f"   If it doesn't open, visit:\n   {authorize_url[:120]}...\n")
    webbrowser.open(authorize_url)

    thread.join(timeout=120)
    server.server_close()

    if server_error[0]:
        print(f"❌ Auth error: {server_error[0]}")
        sys.exit(1)
    if not auth_code[0]:
        print("❌ No auth code received (timeout?)")
        sys.exit(1)

    print("✅ Got authorization code, exchanging for token...")

    # Exchange code for tokens
    token_url = f"{OKTA_ISSUER}/v1/token"
    token_data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": auth_code[0],
        "redirect_uri": CALLBACK_URL,
        "client_id": OKTA_CLIENT_ID,
        "code_verifier": verifier,
    }).encode()

    req = urllib.request.Request(token_url, data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    resp = urllib.request.urlopen(req)
    tokens = json.loads(resp.read())

    access_token = tokens["access_token"]
    print(f"✅ Got user access token (expires in {tokens.get('expires_in', '?')}s)")

    # Decode and show user info (without verification — just for display)
    parts = access_token.split(".")
    if len(parts) == 3:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        print(f"   User: {payload.get('sub', 'unknown')}")
        print(f"   Scopes: {payload.get('scp', [])}")

    return access_token


def invoke_agent(prompt: str, user_token: str = None):
    """Invoke the agent via AgentCore, optionally with a user token for OBO."""
    payload = {"prompt": prompt}
    if user_token:
        payload["user_token"] = user_token

    payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    outfile = "/tmp/agent-obo-response.json"

    cmd = [
        "aws", "bedrock-agentcore", "invoke-agent-runtime",
        "--agent-runtime-arn", RUNTIME_ARN,
        "--qualifier", "DEFAULT",
        "--content-type", "application/json",
        "--payload", payload_b64,
        "--region", "us-east-1",
        outfile,
    ]

    env = os.environ.copy()
    env["AWS_PROFILE"] = AWS_PROFILE

    mode = "OBO (user identity)" if user_token else "service (client_credentials)"
    print(f"\n🚀 Invoking agent via AgentCore (auth mode: {mode})...")

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"❌ AgentCore invoke failed:\n{result.stderr}")
        sys.exit(1)

    meta = json.loads(result.stdout) if result.stdout else {}
    print(f"✅ Response received (session: {meta.get('runtimeSessionId', 'n/a')[:20]}...)")

    with open(outfile) as f:
        response = json.load(f)

    print(f"\n{'='*60}")
    print(f"Agent: {response.get('agent', 'unknown')} | Auth: {response.get('auth_mode', 'unknown')}")
    print(f"{'='*60}")
    print(response.get("output", "(no output)"))
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Invoke DevOps Copilot as an authenticated user")
    parser.add_argument("prompt", help="The prompt to send to the agent")
    parser.add_argument("--service", action="store_true",
                        help="Use client_credentials (service identity) instead of user login")
    args = parser.parse_args()

    if args.service:
        print("📋 Using service identity (client_credentials) — no user login")
        invoke_agent(args.prompt)
    else:
        if not OKTA_CLIENT_ID:
            print("❌ Set OKTA_CLIENT_ID_USER to the native app client ID")
            print("   (from terraform output okta_client_id)")
            sys.exit(1)
        user_token = get_user_token()
        invoke_agent(args.prompt, user_token)


if __name__ == "__main__":
    main()
