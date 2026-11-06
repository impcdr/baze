"""Runtime settings loaded from /home/agent/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path("/home/agent/.env")
DEFAULT_FRONTEND = Path("/home/agent/frontend/dist/frontend/browser")


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
        mongo_db=os.environ.get("MONGODB_DB", "kiln"),
        mongo_auth_source=os.environ.get("MONGODB_AUTH_SOURCE", "admin"),
        api_host=os.environ.get("API_HOST", "0.0.0.0"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        api_token=token,
        frontend_dist=Path(os.environ.get("FRONTEND_DIST", str(DEFAULT_FRONTEND))),
    )
