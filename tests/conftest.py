import pytest

from project import app

@pytest.fixture
def fake_app():
    return app

@pytest.fixture
def client(fake_app):
    fake_app.testing = True
    return fake_app.test_client()
