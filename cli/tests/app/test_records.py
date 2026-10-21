"""Tests for the records commands: list, get, create, update, count, delete."""

from i2g_admin.app import app
from i2g_admin.core.errors import ApiError
from typer.testing import CliRunner

runner = CliRunner()


def test_records_list_with_all_options(use_client):
    client = use_client(get={"results": [{"year": 2025}], "count": 1})
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
    # With no explicit --limit/--offset, U4 auto-pagination drives the request:
    # the first page carries limit/offset (the filter/order/field params it would
    # otherwise carry are absent here), and an empty page terminates cleanly.
    client = use_client(get={"results": [], "count": 0})
    result = runner.invoke(app, ["records", "list", "projects", "semester"])
    assert result.exit_code == 0
    assert client.calls[0][2]["params"] == [("limit", "50"), ("offset", "0")]
    assert len(client.calls) == 1


def test_records_get(use_client):
    use_client(get={"id": "abc"})
    result = runner.invoke(app, ["records", "get", "projects", "semester", "abc"])
    assert result.exit_code == 0


def test_records_create(use_client):
    client = use_client(post={"id": "new"})
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--data", '{"year": 2026, "season": 1}'])
    assert result.exit_code == 0
    assert client.calls[0][2]["json_body"] == {"year": 2026, "season": 1}


def test_records_create_bad_data_exits(use_client):
    use_client(post={"id": "new"})
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--data", "{bad"])
    assert result.exit_code == 1


def test_records_create_missing_data_file_exits(use_client):
    use_client(post={"id": "new"})
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--data", "@/no/such/file.json"])
    assert result.exit_code == 1


def test_records_update(use_client):
    client = use_client(patch={"id": "abc", "is_published": True})
    result = runner.invoke(
        app, ["records", "update", "projects", "semester", "abc", "--data", '{"is_published": true}']
    )
    assert result.exit_code == 0
    assert client.calls[0][2]["json_body"] == {"is_published": True}


def test_records_count(use_client):
    client = use_client(get={"model": "projects.Semester", "count": 3})
    result = runner.invoke(app, ["records", "count", "projects", "semester"])
    assert result.exit_code == 0
    params = client.calls[0][2]["params"]
    assert ("count", "1") in params
    assert all(key != "filter" for key, _ in params)
    assert "3" in result.output


def test_records_count_with_filters(use_client):
    client = use_client(get={"model": "projects.Semester", "count": 1})
    result = runner.invoke(app, ["records", "count", "projects", "semester", "--filter", "year=2051", "--json"])
    assert result.exit_code == 0
    params = client.calls[0][2]["params"]
    assert ("filter", "year=2051") in params
    assert ("count", "1") in params
    assert '"count": 1' in result.output


def test_records_delete_with_yes(use_client):
    use_client(delete={"deleted": True, "cascade": {"total": 0}})
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc", "--yes"])
    assert result.exit_code == 0


def test_records_delete_confirm_cascade(use_client):
    client = use_client(delete={"deleted": True})
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc", "--yes", "--confirm-cascade"])
    assert result.exit_code == 0
    assert client.calls[0][2]["params"] == {"confirm_cascade": "true"}


def test_records_delete_interactive_confirm(use_client):
    use_client(delete={"deleted": True})
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc"], input="y\n")
    assert result.exit_code == 0


def test_records_delete_interactive_abort(use_client):
    use_client(delete={"deleted": True})
    result = runner.invoke(app, ["records", "delete", "projects", "semester", "abc"], input="n\n")
    assert result.exit_code != 0


def test_command_api_error_exits_nonzero(use_client):
    class Raising:
        def get(self, *args, **kwargs):
            raise ApiError(400, "boom")

    use_client(Raising())
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 1
