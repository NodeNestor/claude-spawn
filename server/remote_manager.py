"""Remote Docker manager for claude-spawn — spawn agents on remote Docker hosts."""

from __future__ import annotations

import os
from docker_manager import DockerManager, _run


class RemoteManager(DockerManager):
    """Same as DockerManager but talks to a remote Docker daemon via DOCKER_HOST."""

    def __init__(self, host: str):
        """host: SSH URI like 'ssh://user@server' or TCP like 'tcp://host:2376'."""
        self.host = host
        # Set DOCKER_HOST for all subprocess calls
        os.environ["DOCKER_HOST"] = host

    def spawn(self, **kwargs) -> str:
        result = super().spawn(**kwargs)
        # Tag the output with target info
        if '"status": "running"' in result:
            import json
            info = json.loads(result)
            info["target"] = "remote"
            info["host"] = self.host
            return json.dumps(info, indent=2)
        return result

    def list_agents(self) -> str:
        result = super().list_agents()
        if result.startswith("["):
            import json
            agents = json.loads(result)
            for a in agents:
                a["target"] = "remote"
                a["host"] = self.host
            return json.dumps(agents, indent=2)
        return result

    def status(self, name: str) -> str:
        result = super().status(name)
        if '"status"' in result:
            import json
            try:
                info = json.loads(result)
                info["target"] = "remote"
                info["host"] = self.host
                return json.dumps(info, indent=2)
            except json.JSONDecodeError:
                pass
        return result
