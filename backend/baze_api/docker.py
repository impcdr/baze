"""Docker CLI used to run one Hermes container per live app."""

from __future__ import annotations

import os
import shlex
import subprocess


def _docker_group_visible() -> bool:
    try:
        return os.access("/var/run/docker.sock", os.R_OK | os.W_OK)
    except OSError:
        return False


def docker_command(args: list[str]) -> list[str]:
    if _docker_group_visible():
        return ["docker", *args]
    quoted = " ".join(shlex.quote(part) for part in ["docker", *args])
    return ["sg", "docker", "-c", quoted]


class DockerCli:
    def run(self, args: list[str]) -> str:
        result = subprocess.run(docker_command(args), capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "docker failed").strip()
            raise RuntimeError(detail)
        return result.stdout.strip()

    def remove(self, name: str) -> None:
        subprocess.run(docker_command(["rm", "-f", name]), capture_output=True, text=True)

    def exists(self, name: str) -> bool:
        result = subprocess.run(
            docker_command(["inspect", "-f", "{{.Id}}", name]),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def start(self, name: str) -> None:
        self._checked(["start", name])

    def stop(self, name: str) -> None:
        self._checked(["stop", "-t", "10", name])

    def _checked(self, args: list[str]) -> None:
        result = subprocess.run(docker_command(args), capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "docker failed").strip()
            raise RuntimeError(detail)

    def started_at(self, name: str) -> str | None:
        result = subprocess.run(
            docker_command(["inspect", "-f", "{{.State.StartedAt}}", name]),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        return text or None

    def running(self, name: str) -> bool:
        result = subprocess.run(
            docker_command(["inspect", "-f", "{{.State.Running}}", name]),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"


def open_proxy_from_bridge(image: str, gateway_ip: str, port: int) -> None:
    """Let app containers call the inference proxy on the docker bridge."""
    rule = f"-i docker0 -p tcp -d {gateway_ip} --dport {port} -j ACCEPT"
    script = f"/usr/sbin/iptables -C INPUT {rule} || /usr/sbin/iptables -I INPUT 1 {rule}"
    DockerCli().run(
        [
            "run",
            "--rm",
            "--privileged",
            "--pid",
            "host",
            "--network",
            "host",
            "--user",
            "root",
            "--entrypoint",
            "nsenter",
            image,
            "-t",
            "1",
            "-m",
            "-n",
            "--",
            "/bin/sh",
            "-c",
            script,
        ]
    )


def bridge_gateway() -> str:
    result = subprocess.run(
        docker_command(
            ["network", "inspect", "bridge", "-f", "{{(index .IPAM.Config 0).Gateway}}"]
        ),
        capture_output=True,
        text=True,
    )
    gateway = result.stdout.strip()
    return gateway or "172.17.0.1"
