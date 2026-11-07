import os

os.environ["MONGODB_DB"] = "baze_test"
os.environ["API_TOKEN"] = "test-token-test-token"
os.environ["FRONTEND_DIST"] = "/home/agent/baze/frontend/dist/frontend/browser"

import pytest

from baze_api.app import create_app
from baze_api.db import get_db
from baze_api.settings import load_settings


@pytest.fixture()
def settings():
    return load_settings()


@pytest.fixture(autouse=True)
def clean_db(settings):
    database = get_db(settings)
    for name in ("conversations", "users", "apps", "drafts", "messages"):
        database[name].delete_many({})


@pytest.fixture()
def client(settings):
    return create_app(settings)
