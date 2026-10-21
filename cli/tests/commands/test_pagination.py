"""Tests for U4 auto-pagination: the helper and its wiring into ``records list``."""

import pytest
from i2g_admin import runtime
from i2g_admin.app import app
from i2g_admin.commands.pagination import MAX_PAGE_SIZE, paginate
from i2g_admin.errors import CliError
from typer.testing import CliRunner

runner = CliRunner()

PATH = "/admin-api/records/projects/semester/"


class PageClient:
    """Fake client returning successive canned pages and recording each GET.

    Each entry in ``pages`` is the dict the backend would return for one GET.
    Calls are recorded as ``(path, params)`` so tests can assert the offset/limit
    window the helper walked.
    """

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs.get("params")))
        return self.pages[len(self.calls) - 1]


def _params_map(params):
    return dict(params or [])


# ---- paginate() helper ----------------------------------------------------
def test_no_paginate_single_request():
    client = PageClient([{"model": "m", "count": 99, "results": [{"a": 1}]}])
    result = paginate(client, PATH, [], no_paginate=True, max_items=None, page_size=None)
    assert result == {"model": "m", "count": 99, "results": [{"a": 1}]}
    # A single GET, and base_params is passed through verbatim (no limit/offset added).
    assert len(client.calls) == 1
    assert client.calls[0] == (PATH, [])


def test_no_paginate_preserves_base_params():
    client = PageClient([{"model": "m", "count": 1, "results": [{"a": 1}]}])
    base = [("filter", "year=2025")]
    paginate(client, PATH, base, no_paginate=True, max_items=None, page_size=None)
    assert client.calls[0][1] == [("filter", "year=2025")]
    # The caller's list is not mutated.
    assert base == [("filter", "year=2025")]


def test_multi_page_accumulation():
    # count=5, default page size 50 would fetch all at once; force small pages
    # via page_size to exercise the multi-request loop.
    pages = [
        {"model": "m", "count": 5, "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "count": 5, "results": [{"i": 2}, {"i": 3}]},
        {"model": "m", "count": 5, "results": [{"i": 4}]},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=2)
    assert result["count"] == 5
    assert result["model"] == "m"
    assert [r["i"] for r in result["results"]] == [0, 1, 2, 3, 4]
    # Three pages requested with the right offset window.
    assert len(client.calls) == 3
    assert _params_map(client.calls[0][1]) == {"limit": "2", "offset": "0"}
    assert _params_map(client.calls[1][1]) == {"limit": "2", "offset": "2"}
    assert _params_map(client.calls[2][1]) == {"limit": "2", "offset": "4"}


def test_stops_when_count_reached_without_extra_request():
    # count==len(results) after the first full page: no further GET should fire.
    pages = [{"model": "m", "count": 2, "results": [{"i": 0}, {"i": 1}]}]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=2)
    assert [r["i"] for r in result["results"]] == [0, 1]
    assert len(client.calls) == 1


def test_max_items_truncation_mid_page():
    pages = [
        {"model": "m", "count": 10, "results": [{"i": 0}, {"i": 1}, {"i": 2}]},
        {"model": "m", "count": 10, "results": [{"i": 3}, {"i": 4}, {"i": 5}]},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=4, page_size=3)
    # Exactly max_items rows, truncating the second page.
    assert [r["i"] for r in result["results"]] == [0, 1, 2, 3]
    assert result["count"] == 10
    # Stops once max_items is reached: only two pages fetched.
    assert len(client.calls) == 2


def test_max_items_exact_page_boundary():
    pages = [
        {"model": "m", "count": 10, "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "count": 10, "results": [{"i": 2}, {"i": 3}]},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=2, page_size=2)
    assert [r["i"] for r in result["results"]] == [0, 1]
    # max_items hit exactly at the first page boundary; no second request.
    assert len(client.calls) == 1


def test_empty_first_page_terminates():
    client = PageClient([{"model": "m", "count": 0, "results": []}])
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=None)
    # Accumulated path returns the unified {model, count, offset, limit, results} shape.
    assert result == {"model": "m", "count": 0, "offset": 0, "limit": MAX_PAGE_SIZE, "results": []}
    assert len(client.calls) == 1


def test_empty_page_breaks_even_when_count_overstated():
    # Defensive: server claims more rows than it returns; an empty page must stop
    # the loop instead of spinning forever.
    pages = [
        {"model": "m", "count": 99, "results": [{"i": 0}]},
        {"model": "m", "count": 99, "results": []},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=1)
    assert [r["i"] for r in result["results"]] == [0]
    assert len(client.calls) == 2


def test_page_size_capped_at_max():
    pages = [{"model": "m", "count": 1, "results": [{"i": 0}]}]
    client = PageClient(pages)
    paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=500)
    assert _params_map(client.calls[0][1])["limit"] == str(MAX_PAGE_SIZE)


def test_default_page_size_is_max():
    pages = [{"model": "m", "count": 1, "results": [{"i": 0}]}]
    client = PageClient(pages)
    paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=None)
    assert _params_map(client.calls[0][1])["limit"] == str(MAX_PAGE_SIZE)


def test_base_params_carried_to_every_page():
    pages = [
        {"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "count": 3, "results": [{"i": 2}]},
    ]
    client = PageClient(pages)
    base = [("filter", "year=2025"), ("order", "-year")]
    paginate(client, PATH, base, no_paginate=False, max_items=None, page_size=2)
    for _path, params in client.calls:
        assert ("filter", "year=2025") in params
        assert ("order", "-year") in params
    # Original base list is untouched.
    assert base == [("filter", "year=2025"), ("order", "-year")]


def test_missing_model_and_count_keys_default():
    # A page lacking model/count (older/edge server) should not raise.
    client = PageClient([{"results": []}])
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=None)
    assert result == {"model": None, "count": 0, "offset": 0, "limit": MAX_PAGE_SIZE, "results": []}


# ---- #5: null / missing count must not break or stop early ----------------
def test_null_count_does_not_raise():
    # count=None previously hit `len(accumulated) >= None` -> TypeError.
    pages = [
        {"model": "m", "count": None, "results": [{"i": 0}]},
        {"model": "m", "count": None, "results": []},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=1)
    assert [r["i"] for r in result["results"]] == [0]
    assert result["count"] == 0
    # Two GETs: one row page, then an empty page that terminates.
    assert len(client.calls) == 2


def test_missing_count_key_walks_all_pages():
    # Without a count key, the loop must rely on the empty-page terminator and
    # not stop after the first page (the old `count` default of 0 did: 1 >= 0).
    pages = [
        {"model": "m", "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "results": [{"i": 2}]},
        {"model": "m", "results": []},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=2)
    assert [r["i"] for r in result["results"]] == [0, 1, 2]
    assert len(client.calls) == 3


# ---- #6: negative --max-items is rejected ---------------------------------
def test_negative_max_items_raises():
    client = PageClient([{"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}, {"i": 2}]}])
    with pytest.raises(CliError):
        paginate(client, PATH, [], no_paginate=False, max_items=-1, page_size=50)


def test_negative_max_items_raises_even_with_no_paginate():
    client = PageClient([{"model": "m", "count": 3, "results": [{"i": 0}]}])
    with pytest.raises(CliError):
        paginate(client, PATH, [], no_paginate=True, max_items=-2, page_size=None)


# ---- #7: --no-paginate honors --max-items ---------------------------------
def test_no_paginate_applies_max_items():
    client = PageClient([{"model": "m", "count": 99, "results": [{"i": n} for n in range(50)]}])
    result = paginate(client, PATH, [], no_paginate=True, max_items=5, page_size=None)
    assert [r["i"] for r in result["results"]] == [0, 1, 2, 3, 4]
    # count stays the server-side total; only the rows are truncated.
    assert result["count"] == 99
    assert len(client.calls) == 1


def test_no_paginate_max_items_zero_yields_no_rows():
    client = PageClient([{"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}]}])
    result = paginate(client, PATH, [], no_paginate=True, max_items=0, page_size=None)
    assert result["results"] == []
    assert result["count"] == 3


# ---- #8: all three list shapes agree --------------------------------------
def test_accumulated_shape_includes_offset_and_limit():
    pages = [
        {"model": "m", "count": 3, "results": [{"i": 0}, {"i": 1}]},
        {"model": "m", "count": 3, "results": [{"i": 2}]},
    ]
    client = PageClient(pages)
    result = paginate(client, PATH, [], no_paginate=False, max_items=None, page_size=2)
    assert set(result) == {"model", "count", "offset", "limit", "results"}
    assert result["offset"] == 0
    assert result["limit"] == 2


# ---- records_list wiring (through the CLI) --------------------------------
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
    # #7: --no-paginate must still honor --max-items instead of dumping the page.
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
    # #6: a negative --max-items is a usage error, surfaced as a non-zero exit.
    use_pages([{"model": "m", "count": 1, "results": [{"i": 0}]}])
    result = runner.invoke(
        app,
        ["--max-items", "-1", "records", "list", "projects", "semester"],
    )
    assert result.exit_code == 1
    assert "--max-items must be >= 0." in result.output


def test_cli_negative_max_items_errors_with_explicit_limit(use_pages):
    # #6: the --limit/--offset path bypasses paginate() entirely, so the negative
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
