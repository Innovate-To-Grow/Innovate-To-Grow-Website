"""CLI-level tests for U4 auto-pagination wiring into ``records list``."""

import pytest
from i2g_admin.core import runtime
from i2g_admin.app import app
from test_pagination import _params_map
from typer.testing import CliRunner

runner = CliRunner()


class CliPageClient:
    """A multi-page fake patched onto runtime._client for CLI-level tests."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs.get("params")))
        return self.pages[len(self.calls) - 1]


@pytest.fixture
def use_pages(monkeypatch):
    def install(pages):
        client = CliPageClient(pages)
        monkeypatch.setattr(runtime, "_client", lambda: client)
        return client

    return install


def test_cli_auto_paginates_across_pages(use_pages):
    client = use_pages(
        [
            {"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}]},
            {"model": "m", "count": 3, "results": [{"i": 2}]},
        ]
    )
    result = runner.invoke(
        app,
        ["--output", "json", "--page-size", "2", "records", "list", "projects", "semester"],
    )
    assert result.exit_code == 0
    assert len(client.calls) == 2
    # All three rows surfaced in the rendered JSON.
    assert '"i": 2' in result.output


def test_cli_max_items_truncates(use_pages):
    client = use_pages(
        [
            {"model": "m", "count": 9, "results": [{"i": 0}, {"i": 1}]},
            {"model": "m", "count": 9, "results": [{"i": 2}, {"i": 3}]},
        ]
    )
    result = runner.invoke(
        app,
        [
            "--output",
            "json",
            "--page-size",
            "2",
            "--max-items",
            "3",
            "records",
            "list",
            "projects",
            "semester",
        ],
    )
    assert result.exit_code == 0
    assert '"i": 2' in result.output
    assert '"i": 3' not in result.output


def test_cli_no_paginate_single_request(use_pages):
    client = use_pages([{"model": "m", "count": 99, "results": [{"i": 0}]}])
    result = runner.invoke(
        app,
        ["--no-paginate", "records", "list", "projects", "semester"],
    )
    assert result.exit_code == 0
    assert len(client.calls) == 1
    # --no-paginate sends base params only (no limit/offset injected).
    assert client.calls[0][1] == []


def test_cli_explicit_limit_bypasses_pagination(use_pages):
    client = use_pages([{"model": "m", "count": 99, "results": [{"i": 0}, {"i": 1}]}])
    result = runner.invoke(
        app,
        ["records", "list", "projects", "semester", "--limit", "2"],
    )
    assert result.exit_code == 0
    # Single request honoring the explicit page; no auto follow-up.
    assert len(client.calls) == 1
    assert _params_map(client.calls[0][1]) == {"limit": "2"}


def test_cli_explicit_offset_bypasses_pagination(use_pages):
    client = use_pages([{"model": "m", "count": 99, "results": [{"i": 5}]}])
    result = runner.invoke(
        app,
        ["records", "list", "projects", "semester", "--offset", "5"],
    )
    assert result.exit_code == 0
    assert len(client.calls) == 1
    assert _params_map(client.calls[0][1]) == {"offset": "5"}


def test_cli_no_paginate_with_max_items_truncates(use_pages):
    # --no-paginate must still honor --max-items instead of dumping the page.
    rows = [{"i": n} for n in range(50)]
    client = use_pages([{"model": "m", "count": 99, "results": rows}])
    result = runner.invoke(
        app,
        ["--output", "json", "--no-paginate", "--max-items", "5", "records", "list", "projects", "semester"],
    )
    assert result.exit_code == 0
    assert len(client.calls) == 1
    assert '"i": 4' in result.output
    assert '"i": 5' not in result.output


def test_cli_negative_max_items_errors(use_pages):
    # A negative --max-items is a usage error, surfaced as a non-zero exit.
    use_pages([{"model": "m", "count": 1, "results": [{"i": 0}]}])
    result = runner.invoke(
        app,
        ["--max-items", "-1", "records", "list", "projects", "semester"],
    )
    assert result.exit_code == 1
    assert "--max-items must be >= 0." in result.output


def test_cli_negative_max_items_errors_with_explicit_limit(use_pages):
    # The --limit/--offset path bypasses paginate() entirely, so the negative
    # --max-items guard lives at the global boundary and must reject it here too.
    client = use_pages([{"model": "m", "count": 1, "results": [{"i": 0}]}])
    result = runner.invoke(
        app,
        ["--max-items", "-1", "records", "list", "projects", "semester", "--limit", "5"],
    )
    assert result.exit_code == 1
    assert "--max-items must be >= 0." in result.output
    # Rejected at the boundary, before any request is issued.
    assert len(client.calls) == 0
