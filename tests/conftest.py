import pytest

from project import app, wks

@pytest.fixture
def fake_app():
    return app

@pytest.fixture
def client(fake_app):
    fake_app.testing = True
    return fake_app.test_client()

# @pytest.hookimpl
# def pytest_sessionstart(session):
#     if wks.title != "MEMBERS_FOR_TESTING":
#         pytest.exit("NOT ON TESTING SHEET")
