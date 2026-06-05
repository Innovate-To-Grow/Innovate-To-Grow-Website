import io

import pytest
import typer
from i2g_admin import app as appmod
from i2g_admin import config, runtime
from i2g_admin.app import app
from i2g_admin.errors import ApiError, CliError
from typer.testing import CliRunner

runner = CliRunner()


class FakeClient:
    def __init__(self, **canned):
        self.canned = canned
        self.calls = []

    def _record(self, method, path, kwargs):
        self.calls.append((method, path, kwargs))
        return self.canned.get(method.lower())

    def get(self, path, **kwargs):
        return self._record("GET", path, kwargs)

    def post(self, path, **kwargs):
        return self._record("POST", path, kwargs)

    def patch(self, path, **kwargs):
        return self._record("PATCH", path, kwargs)

    def delete(self, path, **kwargs):
        return self._record("DELETE", path, kwargs)


@pytest.fixture
def use_client(monkeypatch):
    def install(client):
        # Command modules resolve the glue from i2g_admin.runtime; patch it there.
        monkeypatch.setattr(runtime, "_client", lambda: client)
        return client

    return install


# ---- helpers --------------------------------------------------------------
def test_client_builds_api_client(monkeypatch):
    monkeypatch.setattr(appmod.auth, "ensure_token", lambda: ("https://b", "TOK"))
    client = appmod._client()
    assert client.base_url == "https://b"


def test_execute_skips_emit_for_none(capsys):
    appmod._execute(lambda: None, as_json=False)
    assert capsys.readouterr().out == ""


def test_execute_maps_cli_error_to_exit():
    def boom():
        raise ApiError(400, "nope")

    with pytest.raises(typer.Exit):
        appmod._execute(boom)


def test_load_data_inline():
    assert appmod._load_data('{"a": 1}') == {"a": 1}


def test_load_data_from_file(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text('{"b": 2}')
    assert appmod._load_data(f"@{path}") == {"b": 2}


def test_load_data_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"c": 3}'))
    assert appmod._load_data("@-") == {"c": 3}


def test_load_data_invalid_json_raises():
    with pytest.raises(CliError):
        appmod._load_data("{not json")


# ---- commands -------------------------------------------------------------
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
    use_client(FakeClient(get={"member_uuid": "abc", "email": "a@b.c"}))
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 0
    assert "member_uuid" in result.output


def test_whoami_json(use_client):
    use_client(FakeClient(get={"member_uuid": "abc"}))
    result = runner.invoke(app, ["whoami", "--json"])
    assert result.exit_code == 0
    assert "member_uuid" in result.output


def test_models(use_client):
    use_client(FakeClient(get=[{"label": "projects.Semester", "writable": True}]))
    result = runner.invoke(app, ["models"])
    assert result.exit_code == 0


def test_schema(use_client):
    use_client(FakeClient(get={"model": "projects.Semester"}))
    result = runner.invoke(app, ["schema", "projects", "semester"])
    assert result.exit_code == 0


def test_records_list_with_all_options(use_client):
    client = use_client(FakeClient(get={"results": [{"year": 2025}], "count": 1}))
    result = runner.invoke(
        app,
        [
            "records",
            "list",
            "projects",
            "semester",
            "--filter",
            "year=2025",
            "--order",
            "-year",
            "--field",
            "year",
            "--limit",
            "5",
            "--offset",
            "1",
        ],
    )
    assert result.exit_code == 0
    params = client.calls[0][2]["params"]
    assert ("filter", "year=2025") in params
    assert ("order", "-year") in params
    assert ("field", "year") in params
    assert ("limit", "5") in params
    assert ("offset", "1") in params


def test_records_list_no_options(use_client):
    client = use_client(FakeClient(get={"results": [], "count": 0}))
    result = runner.invoke(app, ["records", "list", "projects", "semester"])
    assert result.exit_code == 0
    assert client.calls[0][2]["params"] == []


def test_records_get(use_client):
    use_client(FakeClient(get={"id": "abc"}))
    result = runner.invoke(app, ["records", "get", "projects", "semester", "abc"])
    assert result.exit_code == 0


def test_records_create(use_client):
    client = use_client(FakeClient(post={"id": "new"}))
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--data", '{"year": 2026, "season": 1}'])
    assert result.exit_code == 0
    assert client.calls[0][2]["json_body"] == {"year": 2026, "season": 1}


def test_records_create_bad_data_exits(use_client):
    use_client(FakeClient(post={"id": "new"}))
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--data", "{bad"])
    assert result.exit_code == 1


def test_records_create_missing_data_file_exits(use_client):
    use_client(FakeClient(post={"id": "new"}))
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--data", "@/no/such/file.json"])
    assert result.exit_code == 1


def test_records_update(use_client):
    client = use_client(FakeClient(patch={"id": "abc", "is_published": True}))
    result = runner.invoke(
        app, ["records", "update", "projects", "semester", "abc", "--data", '{"is_published": true}']
    )
    assert result.exit_code == 0
    assert client.calls[0][2]["json_body"] == {"is_published": True}


def test_records_delete_with_yes(use_client):
    use_client(FakeClient(delete={"deleted": True, "cascade": {"total": 0}}))
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc", "--yes"])
    assert result.exit_code == 0


def test_records_delete_confirm_cascade(use_client):
    client = use_client(FakeClient(delete={"deleted": True}))
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc", "--yes", "--confirm-cascade"])
    assert result.exit_code == 0
    assert client.calls[0][2]["params"] == {"confirm_cascade": "true"}


def test_records_delete_interactive_confirm(use_client):
    use_client(FakeClient(delete={"deleted": True}))
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc"], input="y\n")
    assert result.exit_code == 0


def test_records_delete_interactive_abort(use_client):
    use_client(FakeClient(delete={"deleted": True}))
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc"], input="n\n")
    assert result.exit_code != 0


def test_command_api_error_exits_nonzero(use_client):
    class Raising:
        def get(self, *args, **kwargs):
            raise ApiError(400, "boom")

    use_client(Raising())
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 1


# ---- global options & new surface -----------------------------------------
def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "i2g-admin" in result.output


def test_output_json_global_option(use_client):
    use_client(FakeClient(get={"member_uuid": "abc"}))
    result = runner.invoke(app, ["--output", "json", "whoami"])
    assert result.exit_code == 0
    assert '"member_uuid"' in result.output


def test_query_projects_whoami(use_client):
    use_client(FakeClient(get={"member_uuid": "abc", "email": "a@b.c"}))
    result = runner.invoke(app, ["--query", "member_uuid", "--output", "json", "whoami"])
    assert result.exit_code == 0
    assert "abc" in result.output
    assert "email" not in result.output


def test_query_projects_records_list(use_client):
    use_client(FakeClient(get={"results": [{"year": 2025}, {"year": 2026}], "count": 2}))
    result = runner.invoke(
        app, ["--query", "results[*].year", "--output", "json", "records", "list", "projects", "semester"]
    )
    assert result.exit_code == 0
    assert "2025" in result.output
    assert "2026" in result.output
    assert "count" not in result.output


def test_query_invalid_expression_exits(use_client):
    use_client(FakeClient(get={"member_uuid": "abc"}))
    result = runner.invoke(app, ["--query", "!!", "whoami"])
    assert result.exit_code == 1
    assert "Invalid --query expression" in result.output


def test_configure_set_and_get_base_url():
    set_result = runner.invoke(app, ["configure", "set", "base_url", "https://set.example.com"])
    assert set_result.exit_code == 0
    get_result = runner.invoke(app, ["configure", "get", "base_url"])
    assert get_result.exit_code == 0
    assert "https://set.example.com" in get_result.output


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


def test_logout_with_profile(monkeypatch):
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
