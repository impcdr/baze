"""Runtime settings loaded from /home/agent/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path("/home/agent/.env")
DEFAULT_FRONTEND = Path("/home/agent/frontend/dist/frontend/browser")
DEFAULT_APPS_ROOT = Path("/home/agent/baze/data/apps")
DEFAULT_HERMES_IMAGE = (
    "nousresearch/hermes-agent@sha256:adb7890916de63245523492be8f68f9d2095fecbec4e2a6dab7960381f0fc002"
)
DEFAULT_VULTR_BASE = "https://api.vultrinference.com/v1"


@dataclass(frozen=True)
class Settings:
    mongo_host: str
    mongo_port: int
    mongo_username: str
    mongo_password: str
    mongo_db: str
    mongo_auth_source: str
    api_host: str
    api_port: int
    api_token: str
    frontend_dist: Path
    vultr_api_key: str
    vultr_base_url: str
    model_id: str
    reasoning_effort: str
    proxy_port: int
    apps_root: Path
    hermes_image: str
    hermes_port_start: int
    memory_mb: int
    cpus: str
    app_cap: int
    health_timeout: float
    health_interval: float
    ttl_hours: int
    turn_cap: int
    ip_starts_per_hour: int
    ip_starts_per_day: int
    model_calls_per_day: int
    admin_code: str


def load_settings() -> Settings:
    load_dotenv(ENV_PATH, override=False)
    token = os.environ.get("API_TOKEN", "")
    if len(token) < 16:
        raise RuntimeError("API_TOKEN must be set in /home/agent/.env")
    password = os.environ.get("MONGODB_ROOT_PASSWORD", "")
    username = os.environ.get("MONGODB_ROOT_USERNAME", "")
    if not username or not password:
        raise RuntimeError("MongoDB credentials must be set in /home/agent/.env")
    return Settings(
        mongo_host=os.environ.get("MONGODB_HOST", "127.0.0.1"),
        mongo_port=int(os.environ.get("MONGODB_PORT", "27017")),
        mongo_username=username,
        mongo_password=password,
        mongo_db=os.environ.get("MONGODB_DB", "baze"),
        mongo_auth_source=os.environ.get("MONGODB_AUTH_SOURCE", "admin"),
        api_host=os.environ.get("API_HOST", "0.0.0.0"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        api_token=token,
        frontend_dist=Path(os.environ.get("FRONTEND_DIST", str(DEFAULT_FRONTEND))),
        vultr_api_key=os.environ.get("VULTR_INFERENCE_API_KEY", ""),
        vultr_base_url=os.environ.get("VULTR_INFERENCE_BASE_URL", DEFAULT_VULTR_BASE).rstrip("/"),
        model_id=os.environ.get("BAZE_MODEL_ID", "deepseek-v4.1-flash-1017"),
        reasoning_effort=os.environ.get("BAZE_REASONING_EFFORT", "low"),
        proxy_port=int(os.environ.get("BAZE_PROXY_PORT", "8001")),
        apps_root=Path(os.environ.get("BAZE_APPS_ROOT", str(DEFAULT_APPS_ROOT))),
        hermes_image=os.environ.get("HERMES_IMAGE", DEFAULT_HERMES_IMAGE),
        hermes_port_start=int(os.environ.get("BAZE_HERMES_PORT_START", "19080")),
        memory_mb=int(os.environ.get("BAZE_APP_MEMORY_MB", "512")),
        cpus=os.environ.get("BAZE_APP_CPUS", "1"),
        app_cap=int(os.environ.get("BAZE_APP_CAP", "2")),
        health_timeout=float(os.environ.get("BAZE_HEALTH_TIMEOUT", "90")),
        health_interval=float(os.environ.get("BAZE_HEALTH_INTERVAL", "1")),
        ttl_hours=max(1, int(os.environ.get("BAZE_APP_TTL_HOURS", "1"))),
        turn_cap=max(1, int(os.environ.get("BAZE_TURN_CAP", "2"))),
        ip_starts_per_hour=max(1, int(os.environ.get("BAZE_IP_STARTS_PER_HOUR", "4"))),
        ip_starts_per_day=max(1, int(os.environ.get("BAZE_IP_STARTS_PER_DAY", "10"))),
        model_calls_per_day=max(1, int(os.environ.get("BAZE_MODEL_CALLS_PER_DAY", "2000"))),
        admin_code=os.environ.get("BAZE_ADMIN_CODE", ""),
    )
