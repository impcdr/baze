import os

os.environ["MONGODB_DB"] = "kiln_test"
os.environ["API_TOKEN"] = "test-token-test-token"

import pytest

from kiln_api.app import create_app
from kiln_api.db import conversations
from kiln_api.settings import load_settings


@pytest.fixture()
def settings():
    return load_settings()


@pytest.fixture()
def client(settings):
    conversations(settings).delete_many({})
    return create_app(settings)
