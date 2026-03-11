# claude-spawn

You have the claude-spawn plugin installed. Use it to spawn and manage containerized Claude Code agents.

## Tools

| Tool | Use |
|------|-----|
| `spawn_agent` | Create a new agent container. Set `desktop: true` for browser/noVNC, `gpu: true` for NVIDIA GPU. |
| `list_available` | See all available plugins and MCP servers before spawning |
| `list_agents` | See all running agents |
| `agent_status` | Check a specific agent's state and ports |
| `agent_logs` | Read an agent's output |
| `agent_exec` | Run a command inside an agent container |
| `stop_agent` | Stop and remove an agent |

## Plugins (NodeNestor stack)

Our plugins — installed from GitHub repos. Pass in the `plugins` array:
- **rolling-context** — context compression proxy for long sessions
- **knowledge-graph** — persistent cross-session memory
- **workflows** — agent controller with YAML workflows, cron, GitHub polling
- **autoresearch** — auto-research any codebase on first session
- **worktrees** — parallel experimentation via git worktrees

These are cloned from `github.com/NodeNestor/<name>` and registered as Claude Code plugins.

## MCP Servers (third-party)

Third-party MCP servers (npm packages). Pass in the `mcp_servers` array:
- **playwright** — browser automation and testing (default: ON)
- **context7** — live docs for any library (default: ON)
- **filesystem** — file read/write in /workspace
- **github** — GitHub API (needs GITHUB_TOKEN in env)
- **fetch** — HTTP requests
- **memory** — persistent key-value store
- **postgres** — PostgreSQL (needs POSTGRES_CONNECTION_STRING in env)
- **sqlite** — SQLite databases

Use `"all"` for everything, `"none"` to disable all, or pick specific ones.

Call `list_available` to see the full catalog before spawning.

## Workflow

1. **Spawn** an agent with a name, optional prompt, optional repo URL
2. **Monitor** with `agent_logs` and `agent_status`
3. **Interact** with `agent_exec` to run commands inside the container
4. **Stop** when done

## Examples

Spawn a basic agent:
```
spawn_agent(name: "fix-tests", prompt: "Run the tests and fix any failures", repo: "https://github.com/user/repo")
```

Spawn with desktop for browser testing:
```
spawn_agent(name: "e2e-tests", prompt: "Run e2e browser tests", desktop: true)
```

Spawn with plugins:
```
spawn_agent(name: "research", prompt: "Research this codebase", plugins: ["rolling-context", "autoresearch"])
```

Spawn with custom API endpoint (e.g. a proxy):
```
spawn_agent(name: "worker", api_url: "https://my-proxy.example.com/v1", api_key: "sk-...")
```

Spawn with rolling-context through a custom proxy:
```
spawn_agent(name: "long-task", plugins: ["rolling-context"], api_url: "https://my-proxy.example.com")
```

## Notes

- Agents run with `--dangerously-skip-permissions` for autonomous operation
- **Credentials**: by default, mounts the host's `~/.claude/` and `~/.ssh/` read-only. The agent auto-inherits the host's auth.
- **Custom auth**: pass `api_key` and/or `api_url` to override. These are written into the container's settings.json.
- **rolling-context ordering**: when `rolling-context` is in the plugins list, the entrypoint configures the proxy chain automatically — Claude Code -> rolling-context (:5588) -> upstream API. If you also pass a custom `api_url`, rolling-context chains through it.
- Each agent gets its own isolated `/workspace` volume
- Desktop agents expose noVNC on a dynamic port (check `agent_status` for the assigned port)
