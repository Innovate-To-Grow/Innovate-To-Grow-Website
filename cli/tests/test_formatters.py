import json

import pytest
from i2g_admin import formatters
from i2g_admin.errors import CliError


def test_available_formats_includes_builtins_and_stubs():
    names = formatters.available_formats()
    assert {"json", "table", "text", "yaml", "csv"} <= set(names)


def test_get_formatter_unknown_raises():
    with pytest.raises(CliError) as exc:
        formatters.get_formatter("nope")
    assert "Unknown output format" in str(exc.value)


def test_json_formatter_returns_string():
    rendered = formatters.get_formatter("json")({"a": 1})
    assert json.loads(rendered) == {"a": 1}


def test_table_formatter_prints_and_returns_none(capsys):
    assert formatters.get_formatter("table")([{"x": 1}]) is None
    assert "x" in capsys.readouterr().out


def test_table_formatter_empty_list(capsys):
    formatters.get_formatter("table")([])
    assert "no results" in capsys.readouterr().out


def test_table_formatter_scalar(capsys):
    formatters.get_formatter("table")("hello")
    assert "hello" in capsys.readouterr().out


def test_table_formatter_list_of_scalars(capsys):
    formatters.get_formatter("table")(["a", "b"])
    assert "a" in capsys.readouterr().out


@pytest.mark.parametrize("fmt", ["text", "yaml", "csv"])
def test_stub_formats_raise_clear_message(fmt):
    with pytest.raises(CliError) as exc:
        formatters.get_formatter(fmt)({"a": 1})
    assert "not available" in str(exc.value)


def test_register_decorator_adds_entry():
    @formatters.register("temp-fmt")
    def _fmt(data):  # pragma: no cover - exercised below
        return "ok"

    try:
        assert formatters.get_formatter("temp-fmt")(None) == "ok"
    finally:
        formatters.REGISTRY.pop("temp-fmt", None)
