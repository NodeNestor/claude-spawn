# claude-spawn

Spawn containerized Claude Code agents with optional desktop/GPU and SSH access. The orchestrator plugin.

## Install

```bash
/plugin install claude-spawn
```

## What it does

- **Spawn agents** — each agent runs Claude Code in an isolated Docker container
- **Optional desktop** — Xvfb + Chromium + noVNC for browser-based tasks
- **Optional GPU** — NVIDIA runtime passthrough for ML workloads
- **Credential forwarding** — mounts `~/.claude/` and `~/.ssh/` read-only
- **Plugin support** — auto-install rolling-context, knowledge-graph, workflows, autoresearch
- **SSH access** — connect to any agent via SSH
- **tmux sessions** — agents run in tmux for easy attach/detach

## Quick start

Spawn an agent to fix tests:
```
spawn_agent(name: "fix-tests", prompt: "Run tests and fix failures", repo: "https://github.com/user/repo")
```

Spawn with browser for e2e testing:
```
spawn_agent(name: "e2e", desktop: true, prompt: "Run browser e2e tests")
```

With custom API endpoint:
```
spawn_agent(name: "worker", api_url: "https://my-proxy.example.com", api_key: "sk-...")
```

With rolling-context through a proxy:
```
spawn_agent(name: "long-task", plugins: ["rolling-context"], api_url: "https://my-proxy.example.com")
```

Check on it:
```
agent_logs(name: "fix-tests")
agent_status(name: "e2e")
```

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
| `filesystem` | File read/write in /workspace | no |
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
