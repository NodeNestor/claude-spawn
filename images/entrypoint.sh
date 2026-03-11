#!/bin/bash
set -e

echo "=========================================="
echo "claude-spawn — Starting agent..."
echo "  Name: ${AGENT_NAME:-unnamed}"
echo "  Desktop: ${ENABLE_DESKTOP:-false}"
echo "=========================================="

# --- Credentials ---
if [ -d /credentials/claude ]; then
    echo "[credentials] Copying Claude credentials..."
    mkdir -p /home/agent/.claude
    for f in .credentials.json settings.json settings.local.json; do
        [ -f "/credentials/claude/$f" ] && cp "/credentials/claude/$f" "/home/agent/.claude/$f"
    done
    [ -d /credentials/claude/statsig ] && cp -r /credentials/claude/statsig /home/agent/.claude/
    chown -R agent:agent /home/agent/.claude
fi

if [ -d /credentials/ssh ]; then
    echo "[credentials] Copying SSH keys..."
    mkdir -p /home/agent/.ssh
    cp -r /credentials/ssh/. /home/agent/.ssh/
    chmod 700 /home/agent/.ssh
    find /home/agent/.ssh -type f -exec chmod 600 {} \;
    chown -R agent:agent /home/agent/.ssh
fi

if [ -f /credentials/git/.gitconfig ]; then
    echo "[credentials] Copying git config..."
    cp /credentials/git/.gitconfig /home/agent/.gitconfig
    chown agent:agent /home/agent/.gitconfig
fi

# GitHub CLI config
if [ -d /credentials/gh ]; then
    echo "[credentials] Copying GitHub CLI config..."
    mkdir -p /home/agent/.config/gh
    cp -r /credentials/gh/. /home/agent/.config/gh/
    chown -R agent:agent /home/agent/.config/gh

    # If GH_TOKEN is set (extracted from host keyring), write it into hosts.yml
    # so gh CLI works inside the container without keyring
    if [ -n "${GH_TOKEN:-}" ]; then
        echo "[credentials] Injecting GitHub token into gh config..."
        cat > /home/agent/.config/gh/hosts.yml <<GHEOF
github.com:
    oauth_token: ${GH_TOKEN}
    user: ""
    git_protocol: https
GHEOF
        chown agent:agent /home/agent/.config/gh/hosts.yml
    fi
fi

# --- Custom API key ---
# If ANTHROPIC_API_KEY is set via env, write it into settings so Claude Code picks it up.
# This overrides any credentials copied from the host.
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[auth] Using custom API key (env)"
fi

# --- Custom API endpoint ---
# If ANTHROPIC_BASE_URL is set, save the original so rolling-context can chain through it.
if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
    echo "[auth] Custom API endpoint: $ANTHROPIC_BASE_URL"
    export CUSTOM_API_URL="$ANTHROPIC_BASE_URL"
fi

# --- SSH server ---
echo "[ssh] Starting SSH server..."
/usr/sbin/sshd

# --- Desktop (optional) ---
if [ "$ENABLE_DESKTOP" = "true" ]; then
    echo "[desktop] Starting Xvfb..."
    Xvfb :0 -screen 0 1920x1080x24 &
    sleep 1

    echo "[desktop] Starting noVNC on port 6080..."
    websockify --web /usr/share/novnc 6080 localhost:5900 &
fi

# --- Clone repo (optional) ---
if [ -n "${AGENT_REPO:-}" ]; then
    echo "[repo] Cloning $AGENT_REPO..."
    su - agent -c "cd /workspace && git clone '$AGENT_REPO' project" 2>&1 || true
    WORKDIR="/workspace/project"
else
    WORKDIR="/workspace"
fi

# --- Install NodeNestor plugins ---
# Clone from GitHub and run install scripts. These are full Claude Code plugins
# with MCP servers, hooks, skills, etc.
HAS_ROLLING_CONTEXT=false
PLUGINS_DIR="/home/agent/.claude/plugins"
if [ -n "${AGENT_PLUGINS:-}" ]; then
    echo "[plugins] Installing: $AGENT_PLUGINS"
    mkdir -p "$PLUGINS_DIR"
    IFS=',' read -ra PLUGS <<< "$AGENT_PLUGINS"
    for p in "${PLUGS[@]}"; do
        p=$(echo "$p" | xargs)
        [ -z "$p" ] && continue

        if [ "$p" = "rolling-context" ]; then
            HAS_ROLLING_CONTEXT=true
            REPO_NAME="claude-rolling-context"
        else
            REPO_NAME="claude-$p"
        fi

        PLUGIN_DIR="/opt/plugins/$REPO_NAME"
        echo "[plugins] Cloning $REPO_NAME..."
        git clone --depth 1 "https://github.com/NodeNestor/$REPO_NAME.git" "$PLUGIN_DIR" 2>&1 || {
            echo "[plugins] Failed to clone $REPO_NAME, skipping"
            continue
        }

        # Link into Claude's plugin directory
        ln -sf "$PLUGIN_DIR" "$PLUGINS_DIR/$p"

        # Run install script if it exists
        if [ -f "$PLUGIN_DIR/install.sh" ]; then
            echo "[plugins] Running install.sh for $p..."
            if ! su - agent -c "cd '$PLUGIN_DIR' && bash install.sh" 2>&1; then
                echo "[plugins] WARNING: install.sh for $p exited with errors (continuing anyway)"
            fi
        fi

        echo "[plugins] Installed: $p"
    done
    chown -R agent:agent "$PLUGINS_DIR" /opt/plugins 2>/dev/null || true
fi

# --- MCP servers ---
# Register MCP servers from the library based on AGENT_MCP_SERVERS env.
# Default: playwright,context7 (if not specified)
# "none" disables all, "all" enables everything, or comma-separated list.
MCP_LIBRARY="/opt/mcp-library.json"
if [ -f "$MCP_LIBRARY" ]; then
    MCP_SELECTION="${AGENT_MCP_SERVERS:-playwright,context7}"
    echo "[mcp] Configuring MCP servers: $MCP_SELECTION"

    python3 - "$MCP_LIBRARY" "$MCP_SELECTION" <<'PYEOF'
import json, sys, os, subprocess

library_path = sys.argv[1]
selection = sys.argv[2].strip()

with open(library_path) as f:
    library = json.load(f)

all_servers = library.get("mcpServers", {})

if selection == "none":
    selected = {}
elif selection == "all":
    selected = all_servers
else:
    names = [n.strip() for n in selection.split(",") if n.strip()]
    selected = {n: all_servers[n] for n in names if n in all_servers}
    missing = [n for n in names if n not in all_servers]
    if missing:
        print(f"  [warn] Unknown MCP servers: {', '.join(missing)}")

# Filter by requiredEnv
filtered = {}
for name, tool in selected.items():
    required = tool.get("requiredEnv", [])
    has_all = all(os.environ.get(v) for v in required)
    if required and not has_all:
        print(f"  [skip] {name}: missing env {required}")
        continue
    filtered[name] = tool

# Register each via `claude mcp add-json`
for name, tool in filtered.items():
    config = {}
    for key in ("command", "args"):
        if key in tool:
            config[key] = tool[key]

    # Pass requiredEnv values into the MCP server's env
    env_block = {}
    for var in tool.get("requiredEnv", []):
        val = os.environ.get(var, "")
        if val:
            env_block[var] = val
    if env_block:
        config["env"] = env_block

    config_json = json.dumps(config)
    cmd = f"claude mcp add-json -s user {name} '{config_json}' 2>&1"
    try:
        result = subprocess.run(
            ["su", "-", "agent", "-c", cmd],
            capture_output=True, text=True, timeout=15
        )
        print(f"  [ok] {name}")
    except Exception as e:
        print(f"  [err] {name}: {e}")

print(f"  Registered {len(filtered)} MCP server(s)")
PYEOF
fi

# --- Rolling-context proxy setup ---
# rolling-context is a local proxy that must start BEFORE Claude Code.
# It intercepts Claude's API calls for context compression.
# Chain: Claude Code -> rolling-context (:5588) -> upstream API
AGENT_ENV_EXPORTS="export DISPLAY=:0"
if [ "$HAS_ROLLING_CONTEXT" = "true" ]; then
    echo "[rolling-context] Setting up proxy..."
    RC_PORT="${ROLLING_CONTEXT_PORT:-5588}"

    # Determine the real upstream URL
    if [ -n "${CUSTOM_API_URL:-}" ]; then
        # User specified a custom endpoint — rolling-context chains through it
        RC_UPSTREAM="$CUSTOM_API_URL"
        echo "[rolling-context] Chaining through custom upstream: $RC_UPSTREAM"
    else
        RC_UPSTREAM="https://api.anthropic.com"
    fi

    # Write settings.json with rolling-context config
    # This ensures Claude Code talks to the local proxy
    SETTINGS_FILE="/home/agent/.claude/settings.json"
    mkdir -p /home/agent/.claude
    python3 - "$SETTINGS_FILE" "$RC_PORT" "$RC_UPSTREAM" <<'PYEOF'
import json, sys, os
settings_file = sys.argv[1]
rc_port = sys.argv[2]
rc_upstream = sys.argv[3]

settings = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, IOError):
        settings = {}

if "env" not in settings or not isinstance(settings["env"], dict):
    settings["env"] = {}

env = settings["env"]
env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{rc_port}"
env["ROLLING_CONTEXT_UPSTREAM"] = rc_upstream
env["ROLLING_CONTEXT_PORT"] = rc_port
env.setdefault("ROLLING_CONTEXT_TRIGGER", "100000")
env.setdefault("ROLLING_CONTEXT_TARGET", "40000")
env.setdefault("ROLLING_CONTEXT_MODEL", "claude-haiku-4-5-20251001")

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"  ANTHROPIC_BASE_URL=http://127.0.0.1:{rc_port}")
print(f"  ROLLING_CONTEXT_UPSTREAM={rc_upstream}")
PYEOF
    chown -R agent:agent /home/agent/.claude

    # Export env vars for the agent tmux session too
    AGENT_ENV_EXPORTS="$AGENT_ENV_EXPORTS; export ROLLING_CONTEXT_UPSTREAM=$RC_UPSTREAM; export ROLLING_CONTEXT_PORT=$RC_PORT"
elif [ -n "${CUSTOM_API_URL:-}" ]; then
    # No rolling-context, but custom API URL — write it into settings
    SETTINGS_FILE="/home/agent/.claude/settings.json"
    mkdir -p /home/agent/.claude
    python3 - "$SETTINGS_FILE" "$CUSTOM_API_URL" <<'PYEOF'
import json, sys, os
settings_file = sys.argv[1]
api_url = sys.argv[2]

settings = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, IOError):
        settings = {}

if "env" not in settings or not isinstance(settings["env"], dict):
    settings["env"] = {}
settings["env"]["ANTHROPIC_BASE_URL"] = api_url

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"  ANTHROPIC_BASE_URL={api_url}")
PYEOF
    chown -R agent:agent /home/agent/.claude
fi

# If custom API key was provided, write it into settings too
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    SETTINGS_FILE="/home/agent/.claude/settings.json"
    python3 - "$SETTINGS_FILE" "$ANTHROPIC_API_KEY" <<'PYEOF'
import json, sys, os
settings_file = sys.argv[1]
api_key = sys.argv[2]

settings = {}
if os.path.exists(settings_file):
    try:
        with open(settings_file, "r") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, IOError):
        settings = {}

if "env" not in settings or not isinstance(settings["env"], dict):
    settings["env"] = {}
settings["env"]["ANTHROPIC_API_KEY"] = api_key

with open(settings_file, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF
    chown -R agent:agent /home/agent/.claude
fi

# --- Start Claude Code in tmux ---
echo "[agent] Starting Claude Code in tmux..."
CLAUDE_CMD="cd $WORKDIR && claude --dangerously-skip-permissions"
if [ -n "${AGENT_PROMPT:-}" ]; then
    ESCAPED_PROMPT=$(echo "$AGENT_PROMPT" | sed "s/'/'\\\\''/g")
    CLAUDE_CMD="cd $WORKDIR && claude --dangerously-skip-permissions -p '$ESCAPED_PROMPT'"
fi

su - agent -c "
    $AGENT_ENV_EXPORTS
    tmux new-session -d -s agent
    tmux send-keys -t agent '$CLAUDE_CMD' Enter
"

echo "=========================================="
echo "claude-spawn agent ready!"
echo "  tmux: docker exec -it $HOSTNAME su - agent -c 'tmux attach -t agent'"
echo "  SSH:  port 22"
[ "$ENABLE_DESKTOP" = "true" ] && echo "  noVNC: port 6080"
echo "=========================================="

# Keep container alive
exec tail -f /dev/null
