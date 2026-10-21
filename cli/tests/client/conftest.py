import pytest
from i2g_admin import client as client_module


@pytest.fixture
def captured_sleeps(monkeypatch):
    """Patch ``time.sleep`` to record delays without actually waiting."""
    delays = []
    monkeypatch.setattr(client_module.time, "sleep", delays.append)
    return delays
