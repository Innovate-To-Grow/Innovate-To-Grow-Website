"""Make app.py importable however pytest is invoked, and share the test client fixture."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_module  # noqa: E402 - importable only after the path insert above
from app import app  # noqa: E402


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as c:
        # Each test gets a cold cache so stubs aren't masked by cached bodies.
        app_module.cache.clear()
        yield c
