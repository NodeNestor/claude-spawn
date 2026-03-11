# claude-spawn

Spawn containerized Claude Code agents — locally, on Kubernetes, or on remote servers. The orchestrator plugin.

## Install

From the NodeNestor marketplace:
```bash
/plugin marketplace add https://github.com/NodeNestor/nestor-plugins
/plugin install claude-spawn
```

Or manually:
```bash
git clone https://github.com/NodeNestor/claude-spawn.git ~/.claude/plugins/claude-spawn
```

## Usage

Just ask Claude naturally:

> "Spawn an agent to fix the failing tests in this repo"

> "Create an agent on my k8s cluster with GPU to train the model"

> "Spin up an agent on the staging server to run the deploy"

> "How are my agents doing?"

Claude handles the tool calls behind the scenes.

## Targets

| Target | Where it runs | What you need |
|--------|--------------|---------------|
| `local` | Local Docker (default) | Docker |
| `k8s` | Kubernetes cluster | kubectl |
| `remote` | Remote Docker host | SSH access |

```
"Spawn an agent locally to fix tests"
"Spawn an agent on k8s node gpu-node-1 with GPU"
"Spawn an agent on ssh://deploy@prod-server"
```

## What it does

- **Multi-target** — local Docker, Kubernetes pods, or remote Docker hosts
- **Optional desktop** — Xvfb + Chromium + noVNC for browser tasks
- **Optional GPU** — NVIDIA runtime / K8s GPU resources
- **Credential forwarding** — auto-inherits host auth (local: mount, k8s: secret, remote: mount)
- **Plugin support** — auto-install any NodeNestor plugin stack
- **SSH + tmux** — connect to any agent directly

## Plugins (NodeNestor stack)

| Plugin | Description |
|--------|-------------|
| `rolling-context` | Context compression proxy for long sessions |
| `knowledge-graph` | Persistent cross-session memory |
| `workflows` | Agent controller — YAML workflows, cron, GitHub polling |
| `autoresearch` | Auto-research any codebase on first session |
| `worktrees` | Parallel experimentation via git worktrees |

## MCP servers (third-party)

| Server | Description | Default |
|--------|-------------|---------|
| `playwright` | Browser automation and testing | yes |
| `context7` | Live docs for any library | yes |
| `github` | GitHub API (needs GITHUB_TOKEN) | no |
| `fetch` | HTTP requests | no |
| `postgres` | PostgreSQL (needs POSTGRES_CONNECTION_STRING) | no |
| `sqlite` | SQLite databases | no |

## Tools

| Tool | Description |
|------|-------------|
| `spawn_agent` | Create a new agent (any target) |
| `list_available` | See all plugins, MCP servers, and targets |
| `list_agents` | List agents across all targets |
| `agent_status` | Get agent status and ports |
| `agent_logs` | Read agent output |
| `agent_exec` | Run a command in an agent |
| `stop_agent` | Stop and remove an agent |

## Auth

By default, agents inherit credentials from the host. To use custom auth:

- **`api_key`** — custom Anthropic API key
- **`api_url`** — custom API base URL (e.g. a proxy)

When `rolling-context` is in plugins, the proxy chain auto-configures:
```
Claude Code -> rolling-context (:5588) -> api_url (or api.anthropic.com)
```

## Requirements

- Docker (for local/remote targets)
- kubectl (for k8s target)
- Python 3.10+ (for the MCP server)
