#!/usr/bin/env python3
"""Run the official MongoDB image in a rootless OCI container.

Docker is not installed in this environment. crun (under the AppArmor profile
that permits user namespaces) starts mongo:7.0 with the host network namespace
so the database is reachable only on 127.0.0.1.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".mongo"
ROOTFS = Path("/home/agent/.cache/mongodb-container/rootfs")
BUNDLE = ROOT / "bundle"
STATE = ROOT / "crun"
DATA = ROOT / "data"
LOG = ROOT / "mongod.log"
PIDFILE = ROOT / "container.pid"
MARKER = ROOT / "initialized"
CRUN = Path("/home/agent/.local/bin/crun")
CRANE = Path("/home/agent/.local/bin/crane")
ENV_PATH = Path("/home/agent/.env")
CONTAINER = "baze-mongodb"
IMAGE = "mongo:7.0@sha256:e634fcaae4d0915b365fb88c076dd33c851ed61a611c7ee9816aba6d6b5159cd"
PORT = 27017


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def crun_cmd(*args: str) -> list[str]:
    return ["aa-exec", "-p", "crun", "--", str(CRUN), "--root", str(STATE), *args]


def container_status() -> str | None:
    result = subprocess.run(crun_cmd("state", CONTAINER), capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout).get("status")
    except json.JSONDecodeError:
        return None


def port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), 0.4):
            return True
    except OSError:
        return False


def ensure_rootfs() -> None:
    mongod = ROOTFS / "usr/bin/mongod"
    if mongod.is_file() and os.access(mongod, os.X_OK):
        return
    if not CRANE.is_file():
        raise SystemExit(f"missing image tool: {CRANE}")
    if ROOTFS.exists():
        subprocess.run(["rm", "-rf", str(ROOTFS)], check=True)
    ROOTFS.mkdir(parents=True)
    print(f"pulling {IMAGE}", flush=True)
    crane = subprocess.Popen(
        [str(CRANE), "export", "--platform", "linux/amd64", IMAGE, "-"],
        stdout=subprocess.PIPE,
    )
    tar = subprocess.run(["tar", "-C", str(ROOTFS), "-xf", "-"], stdin=crane.stdout)
    assert crane.stdout is not None
    crane.stdout.close()
    crane.wait()
    if crane.returncode != 0 or tar.returncode != 0 or not mongod.is_file():
        raise SystemExit("failed to unpack the MongoDB image")


def write_config(*, auth: bool) -> None:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    (ROOTFS / "data" / "db").mkdir(parents=True, exist_ok=True)
    args = [
        "mongod",
        "--bind_ip",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--dbpath",
        "/data/db",
        "--wiredTigerCacheSizeGB",
        "0.25",
        "--nounixsocket",
    ]
    if auth:
        args.append("--auth")
    config = {
        "ociVersion": "1.0.0",
        "process": {
            "terminal": False,
            "user": {"uid": 0, "gid": 0},
            "args": args,
            "env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME=/tmp",
            ],
            "cwd": "/",
            "noNewPrivileges": True,
            "rlimits": [{"type": "RLIMIT_NOFILE", "hard": 65536, "soft": 65536}],
        },
        "root": {"path": str(ROOTFS), "readonly": False},
        "hostname": "mongodb",
        "mounts": [
            {"destination": "/proc", "type": "proc", "source": "proc"},
            {
                "destination": "/dev",
                "type": "tmpfs",
                "source": "tmpfs",
                "options": ["nosuid", "strictatime", "mode=755", "size=65536k"],
            },
            {
                "destination": "/dev/pts",
                "type": "devpts",
                "source": "devpts",
                "options": ["nosuid", "noexec", "newinstance", "ptmxmode=0666", "mode=0620"],
            },
            {
                "destination": "/dev/shm",
                "type": "tmpfs",
                "source": "shm",
                "options": ["nosuid", "noexec", "nodev", "mode=1777", "size=256m"],
            },
            {"destination": "/sys", "type": "sysfs", "source": "sysfs", "options": ["nosuid", "noexec", "nodev", "ro"]},
            {
                "destination": "/data/db",
                "type": "bind",
                "source": str(DATA),
                "options": ["rbind", "rw"],
            },
        ],
        "linux": {
            "namespaces": [
                {"type": "pid"},
                {"type": "ipc"},
                {"type": "uts"},
                {"type": "user"},
                {"type": "mount"},
            ],
            "maskedPaths": [
                "/proc/acpi",
                "/proc/kcore",
                "/proc/keys",
                "/proc/timer_list",
                "/proc/scsi",
            ],
            "readonlyPaths": ["/proc/bus", "/proc/fs", "/proc/irq", "/proc/sys", "/proc/sysrq-trigger"],
        },
    }
    (BUNDLE / "config.json").write_text(json.dumps(config))


def tail_log() -> None:
    if not LOG.is_file():
        return
    data = LOG.read_bytes()[-4000:]
    sys.stderr.write(data.decode(errors="replace"))
    sys.stderr.write("\n")


def start_container() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    if container_status() is not None:
        subprocess.run(crun_cmd("delete", "--force", CONTAINER), capture_output=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = LOG.open("ab", buffering=0)
    proc = subprocess.Popen(
        crun_cmd("run", "--bundle", str(BUNDLE), CONTAINER),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.close()
    PIDFILE.write_text(str(proc.pid))


def stop_container() -> None:
    if PIDFILE.is_file():
        try:
            os.killpg(int(PIDFILE.read_text().strip()), signal.SIGTERM)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
    if container_status() is not None:
        subprocess.run(crun_cmd("kill", CONTAINER, "TERM"), capture_output=True)
    deadline = time.time() + 20
    while time.time() < deadline and (container_status() == "running" or port_open()):
        time.sleep(0.2)
    if container_status() is not None:
        subprocess.run(crun_cmd("kill", CONTAINER, "KILL"), capture_output=True)
        time.sleep(0.5)
        subprocess.run(crun_cmd("delete", "--force", CONTAINER), capture_output=True)
    if PIDFILE.is_file():
        PIDFILE.unlink()


def wait_ping(*, auth: bool, env: dict[str, str], timeout: float = 60) -> None:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    deadline = time.time() + timeout
    last_error = "not ready"
    while time.time() < deadline:
        if container_status() not in {None, "running", "created"} and not port_open():
            # Give crun a moment to publish state, then fail if it exited.
            time.sleep(0.2)
            if container_status() is None and PIDFILE.is_file():
                try:
                    os.kill(int(PIDFILE.read_text().strip()), 0)
                except OSError:
                    tail_log()
                    raise SystemExit("MongoDB container exited before it was ready")
        try:
            if auth:
                client = MongoClient(
                    host="127.0.0.1",
                    port=PORT,
                    username=env["MONGODB_ROOT_USERNAME"],
                    password=env["MONGODB_ROOT_PASSWORD"],
                    authSource=env.get("MONGODB_AUTH_SOURCE", "admin"),
                    directConnection=True,
                    serverSelectionTimeoutMS=1000,
                )
            else:
                client = MongoClient(
                    host="127.0.0.1",
                    port=PORT,
                    directConnection=True,
                    serverSelectionTimeoutMS=1000,
                )
            client.admin.command("ping")
            client.close()
            return
        except PyMongoError as exc:
            last_error = str(exc)
            time.sleep(0.4)
    tail_log()
    raise SystemExit(f"MongoDB did not become ready ({last_error})")


def credential_hash(env: dict[str, str]) -> str:
    material = f"{env['MONGODB_ROOT_USERNAME']}:{env['MONGODB_ROOT_PASSWORD']}".encode()
    return hashlib.sha256(material).hexdigest()


def create_root_user(env: dict[str, str]) -> None:
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure

    client = MongoClient(host="127.0.0.1", port=PORT, directConnection=True, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command(
            "createUser",
            env["MONGODB_ROOT_USERNAME"],
            pwd=env["MONGODB_ROOT_PASSWORD"],
            roles=[{"role": "root", "db": "admin"}],
        )
    except OperationFailure as exc:
        if exc.code not in {51003, 11000}:
            raise
    finally:
        client.close()


def authenticated(env: dict[str, str]) -> bool:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    try:
        client = MongoClient(
            host="127.0.0.1",
            port=PORT,
            username=env["MONGODB_ROOT_USERNAME"],
            password=env["MONGODB_ROOT_PASSWORD"],
            authSource=env.get("MONGODB_AUTH_SOURCE", "admin"),
            directConnection=True,
            serverSelectionTimeoutMS=1500,
        )
        client.admin.command("ping")
        client.close()
        return True
    except PyMongoError:
        return False


def start() -> None:
    env = load_env()
    for key in ("MONGODB_ROOT_USERNAME", "MONGODB_ROOT_PASSWORD"):
        if not env.get(key):
            raise SystemExit(f"{key} is missing from {ENV_PATH}")
    ensure_rootfs()
    digest = credential_hash(env)
    if MARKER.is_file() and MARKER.read_text().strip() != digest:
        raise SystemExit("MongoDB data was initialized with different credentials. Reset backend/.mongo/data to change them.")
    if container_status() == "running" and authenticated(env):
        print("mongodb already running")
        return
    if container_status() is not None or port_open():
        stop_container()
    if not MARKER.is_file():
        write_config(auth=False)
        start_container()
        wait_ping(auth=False, env=env)
        create_root_user(env)
        stop_container()
        MARKER.write_text(digest + "\n")
    write_config(auth=True)
    start_container()
    wait_ping(auth=True, env=env)
    print(f"mongodb listening on 127.0.0.1:{PORT}")


def status() -> None:
    env = load_env()
    running = container_status()
    print(f"container={running or 'absent'} port={'open' if port_open() else 'closed'} auth={'ok' if authenticated(env) else 'no'}")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    if command == "start":
        start()
    elif command == "stop":
        stop_container()
        print("mongodb stopped")
    elif command == "status":
        status()
    else:
        raise SystemExit("usage: mongodb_container.py start|stop|status")


if __name__ == "__main__":
    main()
