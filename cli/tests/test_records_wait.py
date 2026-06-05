import pytest
from i2g_admin import runtime
from i2g_admin.app import app
from i2g_admin.commands import records_wait
from i2g_admin.errors import CliError
from typer.testing import CliRunner

runner = CliRunner()


class FakeClient:
    """A client whose list endpoint returns successive canned pages of results."""

    def __init__(self, pages):
        # pages: list of "results" lists, one per GET call. The last page repeats.
        self.pages = list(pages)
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        index = min(len(self.calls) - 1, len(self.pages) - 1)
        return {"results": self.pages[index], "count": len(self.pages[index])}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make time.sleep a no-op so polling tests run instantly."""
    monkeypatch.setattr(records_wait.time, "sleep", lambda _seconds: None)


@pytest.fixture
def use_client(monkeypatch):
    def install(client):
        monkeypatch.setattr(runtime, "_client", lambda: client)
        return client

    return install


# ---- parsing --------------------------------------------------------------
def test_parse_until_splits_field_and_value():
    assert records_wait._parse_until("status=done") == ("status", "done")


def test_parse_until_keeps_value_with_equals():
    assert records_wait._parse_until("expr=a=b") == ("expr", "a=b")


def test_parse_until_without_equals_raises():
    with pytest.raises(CliError):
        records_wait._parse_until("status")


def test_parse_until_blank_field_raises():
    with pytest.raises(CliError):
        records_wait._parse_until("=done")


# ---- matching -------------------------------------------------------------
def test_matches_ignores_non_dict_records():
    assert records_wait._matches(["nope", {"status": "done"}], "status", "done") == {"status": "done"}


def test_matches_returns_none_when_field_absent():
    assert records_wait._matches([{"other": 1}], "status", "done") is None


# ---- command: success on first poll ---------------------------------------
def test_wait_condition_met_first_poll(use_client):
    client = use_client(FakeClient([[{"status": "done"}]]))
    result = runner.invoke(
        app,
        ["records", "wait", "projects", "semester", "--until", "status=done", "--filter", "year=2025"],
    )
    assert result.exit_code == 0
    assert "Condition met: status=done." in result.output
    assert len(client.calls) == 1
    assert client.calls[0][1]["params"] == [("filter", "year=2025")]


# ---- command: success after N polls ---------------------------------------
def test_wait_condition_met_after_polls(use_client):
    client = use_client(FakeClient([[{"status": "pending"}], [{"status": "pending"}], [{"status": "done"}]]))
    result = runner.invoke(
        app,
        ["records", "wait", "projects", "semester", "--until", "status=done", "--interval", "1"],
    )
    assert result.exit_code == 0
    assert len(client.calls) == 3


# ---- command: --json emits the matching record ----------------------------
def test_wait_json_emits_record(use_client):
    use_client(FakeClient([[{"status": "done", "id": "abc"}]]))
    result = runner.invoke(
        app,
        ["records", "wait", "projects", "semester", "--until", "status=done", "--json"],
    )
    assert result.exit_code == 0
    assert '"id": "abc"' in result.output


# ---- command: timeout -> exit 1 -------------------------------------------
def test_wait_timeout_exits_nonzero(use_client):
    use_client(FakeClient([[{"status": "pending"}]]))
    result = runner.invoke(
        app,
        ["records", "wait", "projects", "semester", "--until", "status=done", "--timeout", "0"],
    )
    assert result.exit_code == 1
    assert "Timed out" in result.output


# ---- command: bad --until -> exit 1 ---------------------------------------
def test_wait_bad_until_exits_nonzero(use_client):
    use_client(FakeClient([[{"status": "done"}]]))
    result = runner.invoke(app, ["records", "wait", "projects", "semester", "--until", "status"])
    assert result.exit_code == 1


# ---- command: empty / non-dict list payload still times out ---------------
def test_wait_handles_missing_results_key(use_client):
    class NoResults:
        def get(self, path, **kwargs):
            return {"count": 0}

    use_client(NoResults())
    result = runner.invoke(
        app,
        ["records", "wait", "projects", "semester", "--until", "status=done", "--timeout", "0"],
    )
    assert result.exit_code == 1
    assert "Timed out" in result.output
