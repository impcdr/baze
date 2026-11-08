"""Docker CLI used to run one Hermes container per live app."""

from __future__ import annotations

import os
import re
import shlex
import subprocess

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


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

    def logs(self, name: str) -> str:
        """Recent container output. Empty when the box has nothing to show."""
        result = subprocess.run(
            docker_command(["logs", "--tail", "80", name]),
            capture_output=True,
            text=True,
        )
        return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()

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

    def network_gateway(self, name: str) -> str | None:
        result = subprocess.run(
            docker_command(["network", "inspect", "-f", "{{range .IPAM.Config}}{{.Gateway}}{{end}}", name]),
            capture_output=True,
            text=True,
        )
        text = result.stdout.strip()
        if result.returncode != 0 or not _IPV4.match(text):
            return None
        return text

    def inspect_ip(self, name: str) -> str | None:
        result = subprocess.run(
            docker_command(
                ["inspect", "-f", "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name]
            ),
            capture_output=True,
            text=True,
        )
        text = result.stdout.strip()
        if result.returncode != 0 or not _IPV4.match(text):
            return None
        return text

    def exec(self, name: str, command: list[str]) -> None:
        """Run one command in the box. A failing specimen is still a result."""
        subprocess.run(
            docker_command(["exec", "-u", "hermes", "-e", "HOME=/opt/data", name, *command]),
            capture_output=True,
            text=True,
            timeout=20,
        )

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


def _host_args(script: str, image: str) -> list[str]:
    return [
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


def read_host(script: str, image: str) -> str:
    """Run a command on the host. The API uses this to see what a box tried."""
    return DockerCli().run(_host_args(script, image))


def _host_rule(script: str, image: str) -> None:
    read_host(script, image)


def isolate_egress(image: str, container_ip: str, gateway_ip: str, port: int) -> None:
    """Block a container from leaving the host. Name lookup and the inference proxy stay open."""
    if not _IPV4.match(container_ip) or not _IPV4.match(gateway_ip) or not 1 <= int(port) <= 65535:
        raise RuntimeError("Cannot isolate that address")
    destination = int(port)
    dns = "; ".join(_dns_clause(container_ip, proto) for proto in ("udp", "tcp"))
    script = (
        f"iptables -C DOCKER-USER -s {container_ip} -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT "
        f"|| iptables -I DOCKER-USER 1 -s {container_ip} -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT; "
        f"iptables -C DOCKER-USER -s {container_ip} -d {gateway_ip} -p tcp --dport {destination} -j ACCEPT "
        f"|| iptables -I DOCKER-USER 1 -s {container_ip} -d {gateway_ip} -p tcp --dport {destination} -j ACCEPT; "
        f"{dns}; "
        f"iptables -C DOCKER-USER -s {container_ip} -j DROP "
        f"|| iptables -A DOCKER-USER -s {container_ip} -j DROP"
    )
    _host_rule(script, image)


def _dns_clause(container_ip: str, proto: str) -> str:
    rule = f"DOCKER-USER -s {container_ip} -p {proto} --dport 53 -j ACCEPT"
    return f"iptables -C {rule} || iptables -I {rule.replace('DOCKER-USER', 'DOCKER-USER 1', 1)}"


def allow_egress(image: str, container_ip: str, dest_ip: str) -> None:
    """Let one container reach one address on the web ports. The DROP stays behind it."""
    if not _IPV4.match(container_ip) or not _IPV4.match(dest_ip):
        raise RuntimeError("Cannot allow that address")
    script = "; ".join(_allow_clause(container_ip, dest_ip, port) for port in (80, 443))
    _host_rule(script, image)


def clear_allow(image: str, container_ip: str, dest_ip: str) -> None:
    if not _IPV4.match(container_ip) or not _IPV4.match(dest_ip):
        return
    script = "; ".join(
        f"iptables -D DOCKER-USER -s {container_ip} -d {dest_ip} -p tcp --dport {port} -j ACCEPT || true"
        for port in (80, 443)
    )
    _host_rule(script, image)


def _allow_clause(container_ip: str, dest_ip: str, port: int) -> str:
    rule = f"DOCKER-USER -s {container_ip} -d {dest_ip} -p tcp --dport {port} -j ACCEPT"
    return f"iptables -C {rule} || iptables -I {rule.replace('DOCKER-USER', 'DOCKER-USER 1', 1)}"


def release_egress(image: str, container_ip: str, gateway_ip: str, port: int) -> None:
    if not _IPV4.match(container_ip) or not _IPV4.match(gateway_ip):
        return
    destination = int(port)
    dns = "; ".join(
        f"iptables -D DOCKER-USER -s {container_ip} -p {proto} --dport 53 -j ACCEPT || true"
        for proto in ("udp", "tcp")
    )
    script = (
        f"iptables -D DOCKER-USER -s {container_ip} -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || true; "
        f"iptables -D DOCKER-USER -s {container_ip} -d {gateway_ip} -p tcp --dport {destination} -j ACCEPT || true; "
        f"{dns}; "
        f"iptables -D DOCKER-USER -s {container_ip} -j DROP || true"
    )
    _host_rule(script, image)


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
