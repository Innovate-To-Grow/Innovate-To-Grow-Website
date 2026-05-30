import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point the CLI's config dir at a temp location and clear base-url env per test."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("I2G_ADMIN_BASE_URL", raising=False)
    yield
