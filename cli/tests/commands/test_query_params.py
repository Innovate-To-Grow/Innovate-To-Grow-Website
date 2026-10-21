"""Tests for the shared ``records`` query-parameter builders (#12)."""

from i2g_admin.commands.query_params import filter_params, list_query_params


# ---- filter_params --------------------------------------------------------
def test_filter_params_none_yields_empty():
    assert filter_params(None) == []


def test_filter_params_empty_yields_empty():
    assert filter_params([]) == []


def test_filter_params_single():
    assert filter_params(["year=2025"]) == [("filter", "year=2025")]


def test_filter_params_multiple_preserve_order():
    assert filter_params(["year=2025", "season=1"]) == [
        ("filter", "year=2025"),
        ("filter", "season=1"),
    ]


# ---- list_query_params ----------------------------------------------------
def test_list_query_params_all_none():
    assert list_query_params(None, None, None) == []


def test_list_query_params_filters_then_orders_then_fields():
    params = list_query_params(["year=2025"], ["-year"], ["year", "season"])
    assert params == [
        ("filter", "year=2025"),
        ("order", "-year"),
        ("field", "year"),
        ("field", "season"),
    ]


def test_list_query_params_partial_options():
    # Only orders supplied; filters/fields contribute nothing.
    assert list_query_params(None, ["name"], None) == [("order", "name")]
