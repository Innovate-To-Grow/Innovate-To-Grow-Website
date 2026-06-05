import pytest
from i2g_admin.errors import CliError
from i2g_admin.query import run_query


def test_run_query_passthrough_when_no_expression():
    data = {"a": 1}
    assert run_query(data, None) is data
    assert run_query(data, "") is data


def test_run_query_with_expression_not_yet_available():
    with pytest.raises(CliError) as exc:
        run_query({"a": 1}, "a")
    assert "not available" in str(exc.value)
