"""Docker manager for claude-spawn — creates and manages agent containers."""

from __future__ import annotations

import json
import os
import subprocess
import time

CONTAINER_PREFIX = "claude-spawn-"
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_MINIMAL = "claude-spawn:minimal"
IMAGE_DESKTOP = "claude-spawn:desktop"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    """Run a command and return (returncode, stdout+stderr)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        # Prefer stdout; append stderr only on failure
        out = r.stdout.strip()
        if r.returncode != 0 and r.stderr.strip():
            out = (out + "\n" + r.stderr.strip()).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "Command timed out"
    except FileNotFoundError:
        return 1, "docker not found — is Docker installed?"


def _container_name(name: str) -> str:
    return f"{CONTAINER_PREFIX}{name}"


class DockerManager:
    def _home(self) -> str:
        return os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""

    def _creds_dir(self) -> str:
        """Find the Claude credentials directory on the host."""
        claude_dir = os.path.join(self._home(), ".claude")
        if os.path.isdir(claude_dir):
            return claude_dir
        return ""

    def _get_gh_token(self) -> str:
        """Extract GitHub token from gh CLI (works even with keyring auth)."""
        try:
            r = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return ""

    def _build_image(self, desktop: bool) -> tuple[bool, str]:
        """Build the image if it doesn't exist."""
        tag = IMAGE_DESKTOP if desktop else IMAGE_MINIMAL
        dockerfile = "Dockerfile.desktop" if desktop else "Dockerfile.minimal"
        dockerfile_path = os.path.join(SCRIPT_DIR, "images", dockerfile)

        if not os.path.isfile(dockerfile_path):
            return False, f"Dockerfile not found: {dockerfile_path}"

        # Check if image exists
        rc, _ = _run(["docker", "image", "inspect", tag])
        if rc == 0:
            return True, tag

        # Build it
        rc, out = _run(
            ["docker", "build", "-t", tag, "-f", dockerfile_path, os.path.join(SCRIPT_DIR, "images")],
            timeout=600,
        )
        if rc != 0:
            return False, f"Build failed: {out}"
        return True, tag

    def spawn(
        self,
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
    ) -> str:
        cname = _container_name(name)

        # Check if already running
        rc, out = _run(["docker", "inspect", cname])
        if rc == 0:
            return f"Agent '{name}' already exists. Stop it first or use a different name."

        # Build image
        ok, result = self._build_image(desktop)
        if not ok:
            return f"Failed to prepare image: {result}"
        image = result

        # Build docker run command
        cmd = ["docker", "run", "-d", "--name", cname]

        # GPU support
        if gpu:
            cmd += ["--runtime=nvidia", "--gpus", "all"]

        # Mount credentials
        creds = self._creds_dir()
        if creds:
            cmd += ["-v", f"{creds}:/credentials/claude:ro"]

        home = self._home()

        # SSH keys
        ssh_dir = os.path.join(home, ".ssh")
        if os.path.isdir(ssh_dir):
            cmd += ["-v", f"{ssh_dir}:/credentials/ssh:ro"]

        # Git config
        gitconfig = os.path.join(home, ".gitconfig")
        if os.path.isfile(gitconfig):
            cmd += ["-v", f"{gitconfig}:/credentials/git/.gitconfig:ro"]

        # GitHub CLI config
        # Windows: AppData/Roaming/GitHub CLI, Linux/Mac: ~/.config/gh
        gh_dir = os.path.join(home, "AppData", "Roaming", "GitHub CLI")
        if not os.path.isdir(gh_dir):
            gh_dir = os.path.join(home, ".config", "gh")
        if os.path.isdir(gh_dir):
            cmd += ["-v", f"{gh_dir}:/credentials/gh:ro"]

        # Extract gh token for GITHUB_TOKEN env (needed for gh CLI inside container,
        # since keyring won't be available)
        gh_token = self._get_gh_token()
        if gh_token:
            cmd += ["-e", f"GITHUB_TOKEN={gh_token}"]
            cmd += ["-e", f"GH_TOKEN={gh_token}"]

        # Environment
        cmd += ["-e", f"AGENT_NAME={name}"]
        if prompt:
            cmd += ["-e", f"AGENT_PROMPT={prompt}"]
        if repo:
            cmd += ["-e", f"AGENT_REPO={repo}"]
        if plugins:
            cmd += ["-e", f"AGENT_PLUGINS={','.join(plugins)}"]
        if desktop:
            cmd += ["-e", "ENABLE_DESKTOP=true"]
            cmd += ["-p", "6080"]

        # MCP servers selection
        if mcp_servers is not None:
            cmd += ["-e", f"AGENT_MCP_SERVERS={','.join(mcp_servers)}"]

        # Custom API key / endpoint
        if api_key:
            cmd += ["-e", f"ANTHROPIC_API_KEY={api_key}"]
        if api_url:
            cmd += ["-e", f"ANTHROPIC_BASE_URL={api_url}"]

        # Always expose SSH
        cmd += ["-p", "22"]

        # Extra env
        for k, v in (env or {}).items():
            cmd += ["-e", f"{k}={v}"]

        cmd.append(image)

        rc, out = _run(cmd, timeout=60)
        if rc != 0:
            return f"Failed to spawn agent: {out}"

        # Get container ID reliably
        rc2, cid = _run(["docker", "inspect", cname, "--format", "{{.Id}}"])
        container_id = cid[:12] if rc2 == 0 else "unknown"

        # Get assigned ports
        time.sleep(1)
        rc, ports_out = _run(
            ["docker", "port", cname]
        )

        info = {
            "status": "running",
            "name": name,
            "container": cname,
            "id": container_id,
            "image": image,
            "desktop": desktop,
            "gpu": gpu,
            "ports": ports_out if rc == 0 else "unknown",
        }
        if prompt:
            info["prompt"] = prompt[:100] + ("..." if len(prompt) > 100 else "")
        if repo:
            info["repo"] = repo

        return json.dumps(info, indent=2)

    def list_agents(self) -> str:
        rc, out = _run(
            [
                "docker", "ps", "-a",
                "--filter", f"name={CONTAINER_PREFIX}",
                "--format", '{"name":"{{.Names}}","status":"{{.Status}}","image":"{{.Image}}","ports":"{{.Ports}}"}',
            ]
        )
        if rc != 0:
            return f"Failed to list agents: {out}"
        if not out:
            return "No agents running."

        agents = []
        for line in out.strip().split("\n"):
            if line:
                try:
                    a = json.loads(line)
                    a["name"] = a["name"].replace(CONTAINER_PREFIX, "", 1)
                    agents.append(a)
                except json.JSONDecodeError:
                    pass

        return json.dumps(agents, indent=2)

    def status(self, name: str) -> str:
        cname = _container_name(name)
        rc, out = _run(
            ["docker", "inspect", cname, "--format",
             '{"status":"{{.State.Status}}","started":"{{.State.StartedAt}}","image":"{{.Config.Image}}"}']
        )
        if rc != 0:
            return f"Agent '{name}' not found."

        try:
            info = json.loads(out)
        except json.JSONDecodeError:
            info = {"raw": out}

        # Get ports
        rc2, ports = _run(["docker", "port", cname])
        if rc2 == 0:
            info["ports"] = ports

        return json.dumps(info, indent=2)

    def logs(self, name: str, lines: int = 50) -> str:
        cname = _container_name(name)
        rc, out = _run(
            ["docker", "logs", cname, "--tail", str(lines)],
            timeout=10,
        )
        if rc != 0:
            return f"Failed to get logs for '{name}': {out}"
        return out or "(no output)"

    def exec(self, name: str, command: str) -> str:
        cname = _container_name(name)
        rc, out = _run(
            ["docker", "exec", cname, "bash", "-c", command],
            timeout=30,
        )
        if rc != 0:
            return f"Command failed (exit {rc}): {out}"
        return out or "(no output)"

    def stop(self, name: str) -> str:
        cname = _container_name(name)
        rc, out = _run(["docker", "stop", cname], timeout=30)
        if rc != 0:
            return f"Failed to stop '{name}': {out}"
        rc2, out2 = _run(["docker", "rm", cname], timeout=10)
        return f"Agent '{name}' stopped and removed."
