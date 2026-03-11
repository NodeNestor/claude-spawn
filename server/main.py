"""claude-spawn MCP server — spawn and manage containerized Claude Code agents."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from mcp_stdio import MCPServer
from docker_manager import DockerManager

server = MCPServer("claude-spawn", "1.0.0")
dm = DockerManager()


@server.tool(
    "spawn_agent",
    "Spawn a new containerized Claude Code agent",
    {
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent name (used as container name prefix)",
            },
            "prompt": {
                "type": "string",
                "description": "Initial prompt/task for the agent",
            },
            "repo": {
                "type": "string",
                "description": "Git repo URL to clone into the agent workspace (optional)",
            },
            "desktop": {
                "type": "boolean",
                "description": "Enable desktop environment with browser and noVNC (default: false)",
            },
            "gpu": {
                "type": "boolean",
                "description": "Enable GPU passthrough via NVIDIA runtime (default: false)",
            },
            "plugins": {
                "type": "array",
                "items": {"type": "string"},
                "description": "NodeNestor plugins to install: rolling-context, knowledge-graph, workflows, autoresearch, worktrees (default: none)",
            },
            "mcp_servers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "MCP servers to enable: playwright, context7, github, fetch, postgres, sqlite. Defaults: playwright + context7. Pass 'none' to disable all, 'all' for everything.",
            },
            "api_key": {
                "type": "string",
                "description": "Custom Anthropic API key (default: use host credentials)",
            },
            "api_url": {
                "type": "string",
                "description": "Custom API base URL, e.g. a proxy endpoint (default: https://api.anthropic.com)",
            },
            "env": {
                "type": "object",
                "description": "Extra environment variables to pass to the container",
            },
        },
        "required": ["name"],
    },
)
def spawn_agent(
    name: str,
    prompt: str = "",
    repo: str = "",
    desktop: bool = False,
    gpu: bool = False,
    plugins: list = None,
    mcp_servers: list = None,
    api_key: str = "",
    api_url: str = "",
    env: dict = None,
):
    return dm.spawn(
        name=name,
        prompt=prompt,
        repo=repo,
        desktop=desktop,
        gpu=gpu,
        plugins=plugins or [],
        mcp_servers=mcp_servers,
        api_key=api_key,
        api_url=api_url,
        env=env or {},
    )


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
        "mcp_servers": {
            name: {
                "description": s.get("description", ""),
                "category": s.get("category", ""),
                "default": s.get("default", False),
                "requiredEnv": s.get("requiredEnv", []),
            }
            for name, s in mcp.items()
        },
        "defaults": {
            "mcp_servers": ["playwright", "context7"],
            "plugins": [],
        },
    }
    return json.dumps(result, indent=2)


@server.tool(
    "list_agents",
    "List all running claude-spawn agents",
    {"properties": {}, "required": []},
)
def list_agents():
    return dm.list_agents()


@server.tool(
    "agent_status",
    "Get detailed status of a specific agent",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
        },
        "required": ["name"],
    },
)
def agent_status(name: str):
    return dm.status(name)


@server.tool(
    "agent_logs",
    "Get recent logs from an agent container",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
            "lines": {
                "type": "integer",
                "description": "Number of lines to fetch (default: 50)",
            },
        },
        "required": ["name"],
    },
)
def agent_logs(name: str, lines: int = 50):
    return dm.logs(name, lines)


@server.tool(
    "agent_exec",
    "Execute a command inside a running agent container",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
            "command": {"type": "string", "description": "Command to execute"},
        },
        "required": ["name", "command"],
    },
)
def agent_exec(name: str, command: str):
    return dm.exec(name, command)


@server.tool(
    "stop_agent",
    "Stop and remove an agent container",
    {
        "properties": {
            "name": {"type": "string", "description": "Agent name"},
        },
        "required": ["name"],
    },
)
def stop_agent(name: str):
    return dm.stop(name)


if __name__ == "__main__":
    server.run()
