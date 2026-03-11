"""claude-spawn MCP server — spawn and manage containerized Claude Code agents."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mcp_stdio import MCPServer
from docker_manager import DockerManager
from k8s_manager import K8sManager
from remote_manager import RemoteManager

server = MCPServer("claude-spawn", "1.0.0")

# Manager cache — reuse managers across calls
_managers = {}


def _get_manager(target: str = "local", host: str = "", namespace: str = "default"):
    """Get or create the right manager for the target."""
    key = f"{target}:{host}:{namespace}"
    if key not in _managers:
        if target == "k8s":
            _managers[key] = K8sManager(namespace=namespace)
        elif target == "remote":
            if not host:
                raise ValueError("'host' is required for remote target (e.g. 'ssh://user@server')")
            _managers[key] = RemoteManager(host=host)
        else:
            _managers[key] = DockerManager()
    return _managers[key]


@server.tool(
    "spawn_agent",
    "Spawn a new containerized Claude Code agent (locally, on Kubernetes, or on a remote Docker host)",
    {
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent name (used as container/pod name)",
            },
            "prompt": {
                "type": "string",
                "description": "Initial prompt/task for the agent",
            },
            "repo": {
                "type": "string",
                "description": "Git repo URL to clone into the agent workspace",
            },
            "target": {
                "type": "string",
                "enum": ["local", "k8s", "remote"],
                "description": "Where to spawn: 'local' (default Docker), 'k8s' (Kubernetes cluster), 'remote' (remote Docker host)",
            },
            "host": {
                "type": "string",
                "description": "Remote Docker host URI, e.g. 'ssh://user@server'. Only used with target='remote'.",
            },
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace (default: 'default'). Only used with target='k8s'.",
            },
            "node": {
                "type": "string",
                "description": "Kubernetes node hostname to schedule on. Only used with target='k8s'.",
            },
            "desktop": {
                "type": "boolean",
                "description": "Enable desktop environment with browser and noVNC (default: false)",
            },
            "gpu": {
                "type": "boolean",
                "description": "Enable GPU passthrough (default: false)",
            },
            "plugins": {
                "type": "array",
                "items": {"type": "string"},
                "description": "NodeNestor plugins: rolling-context, knowledge-graph, workflows, autoresearch, worktrees",
            },
            "mcp_servers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "MCP servers: playwright, context7, github, fetch, postgres, sqlite. Defaults: playwright + context7.",
            },
            "api_key": {
                "type": "string",
                "description": "Custom Anthropic API key (default: use host credentials)",
            },
            "api_url": {
                "type": "string",
                "description": "Custom API base URL (default: https://api.anthropic.com)",
            },
            "env": {
                "type": "object",
                "description": "Extra environment variables",
            },
        },
        "required": ["name"],
    },
)
def spawn_agent(
    name: str,
    prompt: str = "",
    repo: str = "",
    target: str = "local",
    host: str = "",
    namespace: str = "default",
    node: str = "",
    desktop: bool = False,
    gpu: bool = False,
    plugins: list = None,
    mcp_servers: list = None,
    api_key: str = "",
    api_url: str = "",
    env: dict = None,
):
    try:
        mgr = _get_manager(target, host, namespace)
    except ValueError as e:
        return str(e)

    kwargs = dict(
        name=name, prompt=prompt, repo=repo, desktop=desktop,
        gpu=gpu, plugins=plugins or [], mcp_servers=mcp_servers,
        api_key=api_key, api_url=api_url, env=env or {},
    )
    # K8s-specific params
    if target == "k8s":
        kwargs["namespace"] = namespace
        kwargs["node"] = node

    return mgr.spawn(**kwargs)


@server.tool(
    "list_available",
    "List all available plugins and MCP servers that can be enabled when spawning an agent",
    {"properties": {}, "required": []},
)
def list_available():
    library_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "images", "mcp-library.json",
    )
    mcp = {}
    if os.path.isfile(library_path):
        with open(library_path) as f:
            mcp = json.load(f).get("mcpServers", {})

    result = {
        "plugins (NodeNestor — cloned from GitHub)": {
            "rolling-context": "Context compression proxy — keeps long sessions from hitting token limits",
            "knowledge-graph": "Persistent knowledge graph for cross-session memory",
            "workflows": "Agent controller — YAML workflows for events, cron, GitHub polling",
            "autoresearch": "Auto-research any codebase on first session",
            "worktrees": "Parallel experimentation via git worktrees",
        },
        "mcp_servers (third-party npm)": {
            name: {
                "description": s.get("description", ""),
                "category": s.get("category", ""),
                "default": s.get("default", False),
                "requiredEnv": s.get("requiredEnv", []),
            }
            for name, s in mcp.items()
        },
        "targets": {
            "local": "Local Docker (default)",
            "k8s": "Kubernetes cluster (needs kubectl)",
            "remote": "Remote Docker host (needs host param, e.g. ssh://user@server)",
        },
        "defaults": {
            "target": "local",
            "mcp_servers": ["playwright", "context7"],
            "plugins": [],
        },
    }
    return json.dumps(result, indent=2)


@server.tool(
    "list_agents",
    "List all running claude-spawn agents",
    {
        "properties": {
            "target": {
                "type": "string",
                "enum": ["local", "k8s", "remote", "all"],
                "description": "Which target to list from (default: 'all')",
            },
            "host": {"type": "string", "description": "Remote Docker host (for target='remote')"},
            "namespace": {"type": "string", "description": "K8s namespace (for target='k8s')"},
        },
        "required": [],
    },
)
def list_agents(target: str = "all", host: str = "", namespace: str = "default"):
    if target == "all":
        results = []
        # Local Docker
        local_mgr = _get_manager("local")
        local_result = local_mgr.list_agents()
        if not local_result.startswith("No agents") and not local_result.startswith("Failed"):
            try:
                agents = json.loads(local_result)
                for a in agents:
                    a["target"] = "local"
                results.extend(agents)
            except json.JSONDecodeError:
                pass

        # K8s (only if kubectl is available)
        try:
            k8s_mgr = _get_manager("k8s", namespace=namespace)
            k8s_result = k8s_mgr.list_agents()
            if not k8s_result.startswith("No agents") and not k8s_result.startswith("Failed"):
                results.extend(json.loads(k8s_result))
        except Exception:
            pass

        if not results:
            return "No agents running."
        return json.dumps(results, indent=2)

    try:
        mgr = _get_manager(target, host, namespace)
    except ValueError as e:
        return str(e)
    return mgr.list_agents()


@server.tool(
    "agent_status",
    "Get detailed status of a specific agent",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
            "target": {"type": "string", "enum": ["local", "k8s", "remote"], "description": "Target (default: local)"},
            "host": {"type": "string", "description": "Remote Docker host"},
            "namespace": {"type": "string", "description": "K8s namespace"},
        },
        "required": ["name"],
    },
)
def agent_status(name: str, target: str = "local", host: str = "", namespace: str = "default"):
    try:
        mgr = _get_manager(target, host, namespace)
    except ValueError as e:
        return str(e)
    return mgr.status(name)


@server.tool(
    "agent_logs",
    "Get recent logs from an agent",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
            "lines": {"type": "integer", "description": "Number of lines (default: 50)"},
            "target": {"type": "string", "enum": ["local", "k8s", "remote"], "description": "Target (default: local)"},
            "host": {"type": "string", "description": "Remote Docker host"},
            "namespace": {"type": "string", "description": "K8s namespace"},
        },
        "required": ["name"],
    },
)
def agent_logs(name: str, lines: int = 50, target: str = "local", host: str = "", namespace: str = "default"):
    try:
        mgr = _get_manager(target, host, namespace)
    except ValueError as e:
        return str(e)
    return mgr.logs(name, lines)


@server.tool(
    "agent_exec",
    "Execute a command inside a running agent",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
            "command": {"type": "string", "description": "Command to execute"},
            "target": {"type": "string", "enum": ["local", "k8s", "remote"], "description": "Target (default: local)"},
            "host": {"type": "string", "description": "Remote Docker host"},
            "namespace": {"type": "string", "description": "K8s namespace"},
        },
        "required": ["name", "command"],
    },
)
def agent_exec(name: str, command: str, target: str = "local", host: str = "", namespace: str = "default"):
    try:
        mgr = _get_manager(target, host, namespace)
    except ValueError as e:
        return str(e)
    return mgr.exec(name, command)


@server.tool(
    "stop_agent",
    "Stop and remove an agent",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
            "target": {"type": "string", "enum": ["local", "k8s", "remote"], "description": "Target (default: local)"},
            "host": {"type": "string", "description": "Remote Docker host"},
            "namespace": {"type": "string", "description": "K8s namespace"},
        },
        "required": ["name"],
    },
)
def stop_agent(name: str, target: str = "local", host: str = "", namespace: str = "default"):
    try:
        mgr = _get_manager(target, host, namespace)
    except ValueError as e:
        return str(e)
    return mgr.stop(name)


if __name__ == "__main__":
    server.run()
