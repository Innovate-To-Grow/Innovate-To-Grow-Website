"""Tests for the top-level commands: configure, login, logout, whoami, models, schema, apps."""

from i2g_admin import app as appmod
from i2g_admin import config
from i2g_admin.app import app
from typer.testing import CliRunner

runner = CliRunner()


def test_configure_default(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default.example.com")
    result = runner.invoke(app, ["configure"])
    assert result.exit_code == 0
    assert config.current_base_url() == "https://env-default.example.com"


def test_configure_with_base_url():
    result = runner.invoke(app, ["configure", "--base-url", "http://127.0.0.1:8000"])
    assert result.exit_code == 0
    assert config.current_base_url() == "http://127.0.0.1:8000"


def test_configure_rejects_invalid_base_url(monkeypatch):
    monkeypatch.setenv("I2G_ADMIN_BASE_URL", "https://env-default.example.com")
    result = runner.invoke(app, ["configure", "--base-url", "http://remote.example.com"])
    assert result.exit_code == 1
    # The invalid URL is rejected; the profile keeps the env default.
    assert config.current_base_url() == "https://env-default.example.com"


def test_login(monkeypatch):
    monkeypatch.setattr(appmod.auth, "login", lambda base_url, profile=None: {"access_token": "T"})
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0
    assert "Logged in" in result.output


def test_logout_without_credentials():
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert "No cached credentials" in result.output


def test_logout_with_credentials():
    config.save_credentials({"base_url": "http://b", "access_token": "T"})
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert "Logged out" in result.output


def test_whoami(use_client):
    use_client(get={"member_uuid": "abc", "email": "a@b.c"})
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "member_uuid" in result.output


def test_whoami_json(use_client):
    use_client(get={"member_uuid": "abc"})
    result = runner.invoke(app, ["whoami", "--json"])
    assert result.exit_code == 0
    assert "member_uuid" in result.output


def test_models(use_client):
    use_client(get=[{"label": "projects.Semester", "writable": True}])
    result = runner.invoke(app, ["models"])
    assert result.exit_code == 0


def test_schema(use_client):
    use_client(get={"model": "projects.Semester"})
    result = runner.invoke(app, ["schema", "projects", "semester"])
    assert result.exit_code == 0


def test_apps(use_client):
    client = use_client(
        get={
            "/admin-api/whoami/": {"is_superuser": False, "admin_apps": ["projects"]},
            "/admin-api/apps/": [{"app_label": "projects", "model_count": 3}],
        }
    )
    result = runner.invoke(app, ["apps"])
    assert result.exit_code == 0
    assert [call[1] for call in client.calls] == ["/admin-api/whoami/", "/admin-api/apps/"]
    assert "projects" in result.output


def test_apps_json(use_client):
    use_client(
        get={
            "/admin-api/whoami/": {"is_superuser": False, "admin_apps": ["projects"]},
            "/admin-api/apps/": [{"app_label": "projects", "model_count": 3}],
        }
    )
    result = runner.invoke(app, ["apps", "--json"])
    assert result.exit_code == 0
    assert '"app_label"' in result.output


def test_apps_filters_rows_outside_admin_apps(use_client):
    use_client(
        get={
            "/admin-api/whoami/": {"is_superuser": False, "admin_apps": ["projects"]},
            "/admin-api/apps/": [
                {"app_label": "projects", "model_count": 3},
                {"app_label": "cms", "model_count": 4},
            ],
        }
    )
    result = runner.invoke(app, ["apps", "--json"])
    assert result.exit_code == 0
    assert '"projects"' in result.output
    assert '"cms"' not in result.output


def test_apps_superuser_sees_all_rows(use_client):
    use_client(
        get={
            "/admin-api/whoami/": {"is_superuser": True, "admin_apps": []},
            "/admin-api/apps/": [
                {"app_label": "projects", "model_count": 3},
                {"app_label": "cms", "model_count": 4},
            ],
        }
    )
    result = runner.invoke(app, ["apps", "--json"])
    assert result.exit_code == 0
    assert '"projects"' in result.output
    assert '"cms"' in result.output
