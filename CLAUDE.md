# claude-spawn

You have the claude-spawn plugin installed. Use it to spawn and manage containerized Claude Code agents — locally, on Kubernetes, or on remote Docker hosts.

## Tools

| Tool | Use |
|------|-----|
| `spawn_agent` | Create a new agent. Set `target` to choose where it runs. |
| `list_available` | See all plugins, MCP servers, and targets |
| `list_agents` | See all running agents across all targets |
| `agent_status` | Check a specific agent's state and ports |
| `agent_logs` | Read an agent's output |
| `agent_exec` | Run a command inside an agent |
| `stop_agent` | Stop and remove an agent |

## Targets

| Target | Description | Requirements |
|--------|-------------|-------------|
| `local` | Local Docker (default) | Docker |
| `k8s` | Kubernetes cluster | kubectl with cluster access |
| `remote` | Remote Docker host | SSH access (pass `host: "ssh://user@server"`) |

## Plugins (NodeNestor stack)

Pass in the `plugins` array:
- **rolling-context** — context compression proxy for long sessions
- **knowledge-graph** — persistent cross-session memory
- **workflows** — agent controller with YAML workflows, cron, GitHub polling
- **autoresearch** — auto-research any codebase on first session
- **worktrees** — parallel experimentation via git worktrees

## MCP Servers (third-party)

Pass in the `mcp_servers` array (defaults: playwright + context7):
- **playwright** — browser automation and testing
- **context7** — live docs for any library
- **github** — GitHub API (needs GITHUB_TOKEN)
- **fetch** — HTTP requests
- **postgres** — PostgreSQL (needs POSTGRES_CONNECTION_STRING)
- **sqlite** — SQLite databases

## Examples

Local agent:
```
spawn_agent(name: "fix-tests", prompt: "Fix failing tests", repo: "https://github.com/user/repo")
```

On Kubernetes with GPU:
```
spawn_agent(name: "trainer", target: "k8s", gpu: true, node: "gpu-node-1", prompt: "Train the model")
```

On a remote server:
```
spawn_agent(name: "worker", target: "remote", host: "ssh://deploy@prod-server", prompt: "Deploy and test")
```

With desktop on K8s:
```
spawn_agent(name: "e2e", target: "k8s", desktop: true, prompt: "Run browser e2e tests")
```

Full stack:
```
spawn_agent(name: "research", plugins: ["rolling-context", "knowledge-graph", "autoresearch"], mcp_servers: ["playwright", "context7"])
```

## Notes

- Agents run with `--dangerously-skip-permissions` for autonomous operation
- **Local**: credentials mounted read-only from host `~/.claude/` and `~/.ssh/`
- **K8s**: credentials stored as Kubernetes Secrets, auto-created from host
- **Remote**: same Docker commands, routed via `DOCKER_HOST=ssh://...`
- **rolling-context**: when in plugins, auto-configures proxy chain (Claude Code -> :5588 -> upstream)
- `list_agents` with no target shows agents across all targets
