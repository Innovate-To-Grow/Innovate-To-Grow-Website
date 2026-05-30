import io

import pytest
import typer
from i2g_admin import app as appmod
from i2g_admin import config
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
        monkeypatch.setattr(appmod, "_client", lambda: client)
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
def test_configure_default():
    result = runner.invoke(app, ["configure"])
    assert result.exit_code == 0
    assert config.current_base_url() == config.DEFAULT_BASE_URL


def test_configure_with_base_url():
    result = runner.invoke(app, ["configure", "--base-url", "http://127.0.0.1:8000"])
    assert result.exit_code == 0
    assert config.current_base_url() == "http://127.0.0.1:8000"


def test_configure_rejects_invalid_base_url():
    result = runner.invoke(app, ["configure", "--base-url", "http://remote.example.com"])
    assert result.exit_code == 1
    assert config.current_base_url() == config.DEFAULT_BASE_URL


def test_login(monkeypatch):
    monkeypatch.setattr(appmod.auth, "login", lambda base_url: {"access_token": "T"})
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
