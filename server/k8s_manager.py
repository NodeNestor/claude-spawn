"""Kubernetes manager for claude-spawn — spawn agents as K8s pods."""

from __future__ import annotations

import json
import os
import subprocess

LABEL_KEY = "app.kubernetes.io/managed-by"
LABEL_VALUE = "claude-spawn"
IMAGE_MINIMAL = "ghcr.io/nodenestor/claude-spawn:minimal"
IMAGE_DESKTOP = "ghcr.io/nodenestor/claude-spawn:desktop"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        if r.returncode != 0 and r.stderr.strip():
            out = (out + "\n" + r.stderr.strip()).strip()
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "Command timed out"
    except FileNotFoundError:
        return 1, "kubectl not found — is it installed?"


def _pod_name(name: str) -> str:
    return f"claude-spawn-{name}"


def _build_pod_spec(
    name: str,
    prompt: str = "",
    repo: str = "",
    desktop: bool = False,
    gpu: bool = False,
    plugins: list = None,
    mcp_servers: list = None,
    api_key: str = "",
    api_url: str = "",
    namespace: str = "default",
    node: str = "",
    env: dict = None,
) -> dict:
    """Build a Kubernetes Pod spec."""
    pod_name = _pod_name(name)
    image = IMAGE_DESKTOP if desktop else IMAGE_MINIMAL

    # Environment variables
    env_vars = [
        {"name": "AGENT_NAME", "value": name},
    ]
    if prompt:
        env_vars.append({"name": "AGENT_PROMPT", "value": prompt})
    if repo:
        env_vars.append({"name": "AGENT_REPO", "value": repo})
    if plugins:
        env_vars.append({"name": "AGENT_PLUGINS", "value": ",".join(plugins)})
    if mcp_servers:
        env_vars.append({"name": "AGENT_MCP_SERVERS", "value": ",".join(mcp_servers)})
    if desktop:
        env_vars.append({"name": "ENABLE_DESKTOP", "value": "true"})
    if api_key:
        env_vars.append({"name": "ANTHROPIC_API_KEY", "value": api_key})
    if api_url:
        env_vars.append({"name": "ANTHROPIC_BASE_URL", "value": api_url})
    for k, v in (env or {}).items():
        env_vars.append({"name": k, "value": str(v)})

    # Container spec
    container = {
        "name": "agent",
        "image": image,
        "env": env_vars,
        "ports": [{"containerPort": 22, "name": "ssh"}],
    }

    if desktop:
        container["ports"].append({"containerPort": 6080, "name": "novnc"})

    # GPU resources
    if gpu:
        container["resources"] = {
            "limits": {"nvidia.com/gpu": "1"},
        }

    # Volume mounts for credentials (from K8s secret)
    secret_name = f"claude-spawn-creds-{name}"
    container["volumeMounts"] = [
        {"name": "creds", "mountPath": "/credentials/claude", "readOnly": True},
    ]

    # Pod spec
    spec = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {
                LABEL_KEY: LABEL_VALUE,
                "claude-spawn/agent": name,
            },
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [container],
            "volumes": [
                {
                    "name": "creds",
                    "secret": {
                        "secretName": secret_name,
                        "optional": True,
                    },
                },
            ],
        },
    }

    # Node selector
    if node:
        spec["spec"]["nodeSelector"] = {"kubernetes.io/hostname": node}

    return spec


class K8sManager:
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace

    def _ensure_creds_secret(self, name: str) -> None:
        """Create a K8s secret with Claude credentials from the host."""
        secret_name = f"claude-spawn-creds-{name}"
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
        creds_file = os.path.join(home, ".claude", ".credentials.json")
        settings_file = os.path.join(home, ".claude", "settings.json")

        # Check if secret already exists
        rc, _ = _run(["kubectl", "get", "secret", secret_name, "-n", self.namespace])
        if rc == 0:
            return

        # Build secret from available files
        cmd = [
            "kubectl", "create", "secret", "generic", secret_name,
            "-n", self.namespace,
        ]
        if os.path.isfile(creds_file):
            cmd += [f"--from-file=.credentials.json={creds_file}"]
        if os.path.isfile(settings_file):
            cmd += [f"--from-file=settings.json={settings_file}"]

        _run(cmd)

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
        namespace: str = "",
        node: str = "",
        env: dict = None,
    ) -> str:
        ns = namespace or self.namespace
        pod_name = _pod_name(name)

        # Check if already exists
        rc, _ = _run(["kubectl", "get", "pod", pod_name, "-n", ns])
        if rc == 0:
            return f"Agent '{name}' already exists on k8s. Stop it first or use a different name."

        # Create credentials secret
        if not api_key:
            self._ensure_creds_secret(name)

        # Build and apply pod spec
        spec = _build_pod_spec(
            name=name, prompt=prompt, repo=repo, desktop=desktop,
            gpu=gpu, plugins=plugins, mcp_servers=mcp_servers,
            api_key=api_key, api_url=api_url, namespace=ns,
            node=node, env=env,
        )

        spec_json = json.dumps(spec)
        rc, out = _run(
            ["kubectl", "apply", "-f", "-"],
            timeout=30,
        )
        # kubectl apply -f - needs stdin, use a different approach
        try:
            r = subprocess.run(
                ["kubectl", "apply", "-f", "-", "-n", ns],
                input=spec_json, capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                return f"Failed to create pod: {r.stderr.strip()}"
        except Exception as e:
            return f"Failed to create pod: {e}"

        info = {
            "status": "creating",
            "target": "k8s",
            "name": name,
            "pod": pod_name,
            "namespace": ns,
            "image": IMAGE_DESKTOP if desktop else IMAGE_MINIMAL,
            "desktop": desktop,
            "gpu": gpu,
        }
        if node:
            info["node"] = node
        if prompt:
            info["prompt"] = prompt[:100] + ("..." if len(prompt) > 100 else "")

        return json.dumps(info, indent=2)

    def list_agents(self) -> str:
        rc, out = _run([
            "kubectl", "get", "pods",
            "-l", f"{LABEL_KEY}={LABEL_VALUE}",
            "--all-namespaces",
            "-o", "json",
        ])
        if rc != 0:
            return f"Failed to list agents: {out}"

        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return f"Failed to parse kubectl output: {out}"

        agents = []
        for pod in data.get("items", []):
            meta = pod.get("metadata", {})
            status = pod.get("status", {})
            agents.append({
                "name": meta.get("labels", {}).get("claude-spawn/agent", meta.get("name", "")),
                "pod": meta.get("name", ""),
                "namespace": meta.get("namespace", ""),
                "status": status.get("phase", "Unknown"),
                "node": status.get("hostIP", ""),
                "target": "k8s",
            })

        if not agents:
            return "No agents running on k8s."
        return json.dumps(agents, indent=2)

    def status(self, name: str) -> str:
        pod_name = _pod_name(name)
        rc, out = _run([
            "kubectl", "get", "pod", pod_name,
            "-n", self.namespace, "-o", "json",
        ])
        if rc != 0:
            return f"Agent '{name}' not found on k8s."

        try:
            pod = json.loads(out)
        except json.JSONDecodeError:
            return f"Failed to parse: {out}"

        status = pod.get("status", {})
        info = {
            "name": name,
            "pod": pod_name,
            "phase": status.get("phase", "Unknown"),
            "node": status.get("hostIP", ""),
            "podIP": status.get("podIP", ""),
            "started": status.get("startTime", ""),
            "target": "k8s",
        }

        # Container statuses
        for cs in status.get("containerStatuses", []):
            info["ready"] = cs.get("ready", False)
            info["restarts"] = cs.get("restartCount", 0)

        return json.dumps(info, indent=2)

    def logs(self, name: str, lines: int = 50) -> str:
        pod_name = _pod_name(name)
        rc, out = _run(
            ["kubectl", "logs", pod_name, "-n", self.namespace, "--tail", str(lines)],
            timeout=15,
        )
        if rc != 0:
            return f"Failed to get logs: {out}"
        return out or "(no output)"

    def exec(self, name: str, command: str) -> str:
        pod_name = _pod_name(name)
        rc, out = _run(
            ["kubectl", "exec", pod_name, "-n", self.namespace, "--", "bash", "-c", command],
            timeout=30,
        )
        if rc != 0:
            return f"Command failed: {out}"
        return out or "(no output)"

    def stop(self, name: str) -> str:
        pod_name = _pod_name(name)
        secret_name = f"claude-spawn-creds-{name}"

        rc, out = _run(
            ["kubectl", "delete", "pod", pod_name, "-n", self.namespace, "--grace-period=10"],
            timeout=30,
        )
        if rc != 0:
            return f"Failed to stop: {out}"

        # Clean up credentials secret
        _run(["kubectl", "delete", "secret", secret_name, "-n", self.namespace, "--ignore-not-found"])

        return f"Agent '{name}' stopped and removed from k8s."
