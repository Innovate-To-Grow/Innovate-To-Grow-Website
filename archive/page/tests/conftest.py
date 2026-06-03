import pytest

from project import app

# Set testing mode BEFORE importing wks so __init__.py uses the test sheet
app.testing = True

from project import sh
@pytest.fixture
def fake_app():
    return app


@pytest.fixture
def client(fake_app):
    fake_app.testing = True
    return fake_app.test_client()


@pytest.hookimpl
def pytest_sessionstart(session):
    if sh.title != "Test I2G Membership":
        pytest.exit("NOT ON TESTING SHEET - Must use 'Test I2G Membership' worksheet")
