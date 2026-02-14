# Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AWS AgentCore (us-east-1)                 │
│                                                             │
│  ┌─────────────────────┐    ┌────────────────────────────┐  │
│  │   Agent Runtime     │    │       Gateway (MCP)        │  │
│  │   (DevOps Copilot)  │    │                            │  │
│  │                     │    │  ┌──────────────────────┐  │  │
│  │  ┌───────────────┐  │    │  │  Gateway Target      │  │  │
│  │  │ Container     │  │───▶│  │  (mcpServer)         │  │  │
│  │  │ (ECR image)   │  │    │  │                      │  │  │
│  │  └───────────────┘  │    │  └──────────┬───────────┘  │  │
│  │                     │    │             │              │  │
│  │  ┌───────────────┐  │    └─────────────┼──────────────┘  │
│  │  │ Endpoint      │  │                  │                 │
│  │  │ (public URL)  │  │                  │                 │
│  │  └───────────────┘  │                  │                 │
│  └─────────────────────┘                  │                 │
│                                           │                 │
│  ┌─────────────────────┐                  │                 │
│  │ IAM Roles           │                  │                 │
│  │ • Runtime role      │                  │                 │
│  │ • Gateway role      │                  │                 │
│  └─────────────────────┘                  │                 │
│                                           │                 │
│  ┌─────────────────────┐                  │                 │
│  │ ECR Repository      │                  │                 │
│  │ (agent container)   │                  │                 │
│  └─────────────────────┘                  │                 │
└───────────────────────────────────────────┼─────────────────┘
                                            │
                                            │ HTTPS (ngrok/public URL)
                                            │
                    ┌───────────────────────────────────────┐
                    │  k8s-rooster (172.16.10.168)          │
                    │                                       │
                    │  ┌─────────────────────────────────┐  │
                    │  │      AgentGateway               │  │
                    │  │                                 │  │
                    │  │  ┌──────────┐  ┌────────────┐  │  │
                    │  │  │ LLM      │  │ MCP Tools  │  │  │
                    │  │  │ Routes   │  │ Routes     │  │  │
                    │  │  └──────────┘  └────────────┘  │  │
                    │  └─────────────────────────────────┘  │
                    └───────────────────────────────────────┘
```

## Components

### AWS AgentCore
- **Agent Runtime**: Runs the DevOps Copilot container from ECR
- **Runtime Endpoint**: Public-facing endpoint for the runtime
- **Gateway**: MCP protocol gateway connecting to external services
- **Gateway Target**: Points to AgentGateway on k8s-rooster via public URL

### k8s-rooster Cluster
- **AgentGateway**: Routes requests to LLM providers and MCP tool servers
- Needs a public endpoint (ngrok or similar) for AgentCore to reach it

### Future: Okta Integration
- OAuth2 credential provider for on-behalf-of (OBO) token flow
- Workload identity for agent-to-service authentication

## Data Flow

1. Client invokes agent via AgentCore Runtime Endpoint
2. AgentCore runs the container, which processes the request
3. Agent calls tools via AgentCore Gateway (MCP protocol)
4. Gateway routes to AgentGateway on k8s-rooster
5. AgentGateway fans out to LLM providers and MCP tool servers
6. Response flows back through the chain

## Terraform Resources

| Resource | Type | Provider |
|----------|------|----------|
| ECR Repository | Native | `aws` |
| IAM Roles & Policies | Native | `aws` |
| Agent Runtime | `null_resource` + local-exec | AWS CLI |
| Runtime Endpoint | `null_resource` + local-exec | AWS CLI |
| Gateway | `null_resource` + local-exec | AWS CLI |
| Gateway Target | `null_resource` + local-exec | AWS CLI |
| OAuth2 Credential | Placeholder | — |
