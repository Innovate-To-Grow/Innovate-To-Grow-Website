import pytest
from i2g_admin.errors import CliError
from i2g_admin.query import run_query


def test_run_query_passthrough_when_no_expression():
    data = {"a": 1}
    assert run_query(data, None) is data
    assert run_query(data, "") is data


def test_run_query_projects_nested_key_from_dict():
    assert run_query({"a": {"b": 5}}, "a.b") == 5


def test_run_query_projects_field_from_list_of_dicts():
    payload = {"results": [{"field": 1}, {"field": 2}, {"field": 3}]}
    assert run_query(payload, "results[*].field") == [1, 2, 3]


def test_run_query_missing_key_returns_none():
    assert run_query({"a": 1}, "b") is None


def test_run_query_invalid_expression_raises_cli_error():
    with pytest.raises(CliError) as exc:
        run_query({"a": 1}, "!!")
    assert "Invalid --query expression" in str(exc.value)
