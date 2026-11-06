import os

os.environ["MONGODB_DB"] = "baze_test"
os.environ["API_TOKEN"] = "test-token-test-token"

import pytest

from baze_api.app import create_app
from baze_api.db import conversations
from baze_api.settings import load_settings


@pytest.fixture()
def settings():
    return load_settings()


@pytest.fixture()
def client(settings):
    conversations(settings).delete_many({})
    return create_app(settings)
