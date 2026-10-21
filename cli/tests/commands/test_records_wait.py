"""Unit tests for records_wait parsing and record matching."""

import pytest
from i2g_admin.commands.records import wait as records_wait
from i2g_admin.core.errors import CliError


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


# ---- bool / None / numeric matching with natural spellings ----------------
def test_matches_bool_true_natural_spelling():
    record = {"is_published": True}
    assert records_wait._matches([record], "is_published", "true") == record
    assert records_wait._matches([record], "is_published", "TRUE") == record


def test_matches_bool_false_natural_spelling():
    record = {"is_published": False}
    assert records_wait._matches([record], "is_published", "false") == record
    # A False value must not match the "true" expectation.
    assert records_wait._matches([record], "is_published", "true") is None


def test_matches_bool_repr_still_works():
    # The Python repr (True/False) keeps matching for back-compat.
    assert records_wait._matches([{"flag": True}], "flag", "True") == {"flag": True}


def test_matches_none_with_null():
    record = {"archived_at": None}
    assert records_wait._matches([record], "archived_at", "null") == record
    assert records_wait._matches([record], "archived_at", "none") == record


def test_matches_none_does_not_match_other_text():
    assert records_wait._matches([{"archived_at": None}], "archived_at", "done") is None


def test_matches_none_not_matched_by_empty_spelling():
    # An empty (or whitespace-only) --until value waits for a genuine empty string,
    # not null — they must never be conflated. `field=null` is the way to match None.
    assert records_wait._matches([{"archived_at": None}], "archived_at", "") is None
    assert records_wait._matches([{"archived_at": None}], "archived_at", "   ") is None


def test_matches_empty_string_value():
    # An empty expected value matches a genuine empty-string field...
    assert records_wait._matches([{"note": ""}], "note", "") == {"note": ""}
    # ...but not a null field (no conflation between "" and None).
    assert records_wait._matches([{"note": None}], "note", "") is None


def test_matches_numeric_value():
    record = {"year": 2025}
    assert records_wait._matches([record], "year", "2025") == record
    assert records_wait._matches([record], "year", "2024") is None


def test_matches_string_value():
    assert records_wait._matches([{"status": "done"}], "status", "done") == {"status": "done"}
    assert records_wait._matches([{"status": "pending"}], "status", "done") is None
