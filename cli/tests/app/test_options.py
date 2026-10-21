"""Tests for global options: --version, --output, --query, profiles, --debug."""

from i2g_admin import app as appmod
from i2g_admin import config
from i2g_admin.core import runtime
from i2g_admin.app import app
from i2g_admin.core.errors import ApiError
from typer.testing import CliRunner

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "i2g-admin" in result.output


def test_output_json_global_option(use_client):
    use_client(get={"member_uuid": "abc"})
    result = runner.invoke(app, ["--output", "json", "whoami"])
    assert result.exit_code == 0
    assert '"member_uuid"' in result.output


def test_query_projects_whoami(use_client):
    use_client(get={"member_uuid": "abc", "email": "a@b.c"})
    result = runner.invoke(app, ["--query", "member_uuid", "--output", "json", "whoami"])
    assert result.exit_code == 0
    assert "abc" in result.output
    assert "email" not in result.output


def test_query_projects_records_list(use_client):
    use_client(get={"results": [{"year": 2025}, {"year": 2026}], "count": 2})
    result = runner.invoke(
        app, ["--query", "results[*].year", "--output", "json", "records", "list", "projects", "semester"]
    )
    assert result.exit_code == 0
    assert "2025" in result.output
    assert "2026" in result.output
    assert "count" not in result.output


def test_query_invalid_expression_exits(use_client):
    use_client(get={"member_uuid": "abc"})
    result = runner.invoke(app, ["--query", "!!", "whoami"])
    assert result.exit_code == 1
    assert "Invalid --query expression" in result.output


def test_configure_set_and_get_base_url():
    set_result = runner.invoke(app, ["configure", "set", "base_url", "https://set.example.com"])
    assert set_result.exit_code == 0
    get_result = runner.invoke(app, ["configure", "get", "base_url"])
    assert get_result.exit_code == 0
    assert get_result.output.strip() == "https://set.example.com"


def test_configure_set_unknown_key_errors():
    result = runner.invoke(app, ["configure", "set", "nope", "x"])
    assert result.exit_code == 1
    assert "Unknown config key" in result.output


def test_configure_get_unknown_key_errors():
    result = runner.invoke(app, ["configure", "get", "nope"])
    assert result.exit_code == 1
    assert "Unknown config key" in result.output


def test_configure_list_shows_profiles():
    config.set_base_url("https://stg.example.com", profile="staging")
    result = runner.invoke(app, ["configure", "list"])
    assert result.exit_code == 0
    assert "staging" in result.output


def test_profile_threads_through_to_credentials(monkeypatch):
    captured = {}

    def fake_login(base_url, profile=None):
        captured["profile"] = profile

    monkeypatch.setattr(appmod.auth, "login", fake_login)
    config.set_base_url("https://stg.example.com", profile="staging")
    result = runner.invoke(app, ["--profile", "staging", "login"])
    assert result.exit_code == 0
    assert captured["profile"] == "staging"


def test_logout_with_profile():
    config.save_credentials({"access_token": "T"}, profile="staging")
    result = runner.invoke(app, ["--profile", "staging", "logout"])
    assert result.exit_code == 0
    assert "Logged out" in result.output


def test_client_factory_uses_context_build_client(monkeypatch):
    # _client() with an active CLI context delegates to build_client(context).
    seen = {}

    class RecordingClient:
        def get(self, path, **kwargs):
            return {"member_uuid": "abc"}

    def fake_build_client(context):
        seen["profile"] = context.profile
        return RecordingClient()

    # _client() resolves build_client from the runtime module; patch it there.
    monkeypatch.setattr(runtime, "build_client", fake_build_client)
    result = runner.invoke(app, ["--profile", "prod", "whoami"])
    assert result.exit_code == 0
    assert seen["profile"] == "prod"


def test_client_factory_without_context(monkeypatch):
    # Direct call (no CLI context) uses the legacy zero-arg token lookup.
    monkeypatch.setattr(runtime.auth, "ensure_token", lambda: ("https://b", "TOK"))
    client = runtime._client()
    assert client.base_url == "https://b"


def test_debug_flag_prints_error_repr(use_client):
    class Raising:
        def get(self, *args, **kwargs):
            raise ApiError(400, "boom detail")

    use_client(Raising())
    result = runner.invoke(app, ["--debug", "whoami"])
    assert result.exit_code == 1
    # --debug adds the repr() of the error (includes the class name).
    assert "ApiError" in result.output


def test_invalid_profile_name_errors():
    result = runner.invoke(app, ["--profile", "bad/name", "configure", "get", "base_url"])
    assert result.exit_code == 1
    assert "Invalid profile name" in result.output
