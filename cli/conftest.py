import pytest

# A valid https base URL for tests that exercise the happy path. The CLI has no
# baked-in default base URL (it is env/.env/configure-driven by design), so tests
# supply one here; cases that specifically test "missing base URL" delete it.
TEST_BASE_URL = "https://testserver.local"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Point the CLI's config dir at a temp location and provide a default base URL per test."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", TEST_BASE_URL)
    yield
