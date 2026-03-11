# claude-spawn

Spawn containerized Claude Code agents with optional desktop/GPU and SSH access. The orchestrator plugin.

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

> "Create an agent with a browser to run e2e tests"

> "Spin up an agent with rolling-context and autoresearch to work on this long task"

> "How are my agents doing?"

Claude handles the MCP tool calls behind the scenes. You never need to call tools directly.

## What it does

- **Spawn agents** — each agent runs Claude Code in an isolated Docker container
- **Optional desktop** — Xvfb + Chromium + noVNC for browser-based tasks
- **Optional GPU** — NVIDIA runtime passthrough for ML workloads
- **Credential forwarding** — mounts `~/.claude/` and `~/.ssh/` read-only
- **Plugin support** — auto-install rolling-context, knowledge-graph, workflows, autoresearch
- **SSH access** — connect to any agent via SSH
- **tmux sessions** — agents run in tmux for easy attach/detach

## Quick start

Just tell Claude what you want:

```
"Spawn an agent called fix-tests to clone github.com/user/repo and fix the failing tests"
"Spin up an agent with a desktop browser for e2e testing"
"Create an agent with rolling-context and autoresearch plugins"
"Check the logs on my fix-tests agent"
"Stop all agents"
```

Under the hood, Claude calls MCP tools like `spawn_agent`, `agent_logs`, `stop_agent`, etc.

## Plugins (NodeNestor stack)

Installed from GitHub repos. Pass in `plugins` array:

| Plugin | Description |
|--------|-------------|
| `rolling-context` | Context compression proxy for long sessions |
| `knowledge-graph` | Persistent cross-session memory |
| `workflows` | Agent controller — YAML workflows, cron, GitHub polling |
| `autoresearch` | Auto-research any codebase on first session |
| `worktrees` | Parallel experimentation via git worktrees |

## MCP servers (third-party)

npm packages registered via `claude mcp add-json`. Pass in `mcp_servers` array:

| Server | Description | Default |
|--------|-------------|---------|
| `playwright` | Browser automation and testing | yes |
| `context7` | Live docs for any library | yes |
| `github` | GitHub API (needs GITHUB_TOKEN) | no |
| `fetch` | HTTP requests | no |
| `memory` | Persistent key-value store | no |
| `postgres` | PostgreSQL (needs POSTGRES_CONNECTION_STRING) | no |
| `sqlite` | SQLite databases | no |

Use `"all"` for everything, `"none"` to disable all.

## MCP tools

| Tool | Description |
|------|-------------|
| `spawn_agent` | Create a new agent container |
| `list_available` | See all plugins and MCP servers |
| `list_agents` | List all agents |
| `agent_status` | Get agent status and ports |
| `agent_logs` | Read agent output |
| `agent_exec` | Run a command in an agent |
| `stop_agent` | Stop and remove an agent |

## Images

| Image | Contents |
|-------|----------|
| `claude-spawn:minimal` | Ubuntu 24.04, Python 3, Node.js 22, Claude Code, SSH, tmux |
| `claude-spawn:desktop` | Minimal + Xvfb, Chromium, noVNC (port 6080) |

Images are built automatically on first spawn.

## Auth

By default, agents inherit credentials from the host's `~/.claude/` (mounted read-only). To use custom auth:

- **`api_key`** — custom Anthropic API key
- **`api_url`** — custom API base URL (e.g. a proxy like CodeGate)

When `rolling-context` is in the plugins list, the entrypoint auto-configures the proxy chain:
```
Claude Code -> rolling-context (:5588) -> api_url (or api.anthropic.com)
```

## Requirements

- Docker
- Python 3.10+ (for the MCP server)
