import csv
import io
import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
import yaml
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


# --- text formatter ---------------------------------------------------------
def test_text_list_of_dicts():
    rendered = formatters.get_formatter("text")([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
    assert rendered == "1\t2\n3\t4"


def test_text_single_dict():
    rendered = formatters.get_formatter("text")({"a": 1, "b": "two"})
    assert rendered == "1\ttwo"


def test_text_list_of_scalars():
    rendered = formatters.get_formatter("text")(["a", "b", "c"])
    assert rendered == "a\nb\nc"


def test_text_scalar():
    assert formatters.get_formatter("text")(42) == "42"


def test_text_empty_list():
    assert formatters.get_formatter("text")([]) == ""


def test_text_none_values_render_empty():
    rendered = formatters.get_formatter("text")({"a": None, "b": 2})
    assert rendered == "\t2"


def test_text_list_of_mixed_dict_and_scalar():
    rendered = formatters.get_formatter("text")([{"a": 1}, "scalar"])
    assert rendered == "1\nscalar"


# --- yaml formatter ---------------------------------------------------------
def test_yaml_list_of_dicts_sorted_keys():
    rendered = formatters.get_formatter("yaml")([{"b": 2, "a": 1}])
    assert yaml.safe_load(rendered) == [{"a": 1, "b": 2}]
    # keys are emitted in stable (sorted) order regardless of input order
    assert rendered.index("a:") < rendered.index("b:")


def test_yaml_single_dict():
    rendered = formatters.get_formatter("yaml")({"a": 1, "b": 2})
    assert yaml.safe_load(rendered) == {"a": 1, "b": 2}


def test_yaml_list_of_scalars():
    rendered = formatters.get_formatter("yaml")(["a", "b"])
    assert yaml.safe_load(rendered) == ["a", "b"]


def test_yaml_scalar():
    assert yaml.safe_load(formatters.get_formatter("yaml")(42)) == 42


def test_yaml_empty_list():
    assert yaml.safe_load(formatters.get_formatter("yaml")([])) == []


def test_yaml_normalizes_non_json_native_values():
    data = {
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "when": datetime(2024, 1, 2, 3, 4, 5),
        "amount": Decimal("1.50"),
    }
    rendered = formatters.get_formatter("yaml")(data)
    loaded = yaml.safe_load(rendered)
    assert loaded == {
        "id": "12345678-1234-5678-1234-567812345678",
        "when": "2024-01-02 03:04:05",
        "amount": "1.50",
    }


# --- csv formatter ----------------------------------------------------------
def _parse_csv(rendered):
    return list(csv.reader(io.StringIO(rendered)))


def test_csv_list_of_dicts_union_of_keys():
    rendered = formatters.get_formatter("csv")([{"a": 1, "b": 2}, {"a": 3, "c": 4}])
    rows = _parse_csv(rendered)
    assert rows[0] == ["a", "b", "c"]  # union, first-seen order
    assert rows[1] == ["1", "2", ""]  # missing key -> empty cell
    assert rows[2] == ["3", "", "4"]


def test_csv_single_dict_key_value():
    rendered = formatters.get_formatter("csv")({"a": 1, "b": "two"})
    rows = _parse_csv(rendered)
    assert rows[0] == ["key", "value"]
    assert rows[1] == ["a", "1"]
    assert rows[2] == ["b", "two"]


def test_csv_list_of_scalars_one_per_line():
    rendered = formatters.get_formatter("csv")(["a", "b", "c"])
    rows = _parse_csv(rendered)
    assert rows == [["a"], ["b"], ["c"]]


def test_csv_scalar():
    rendered = formatters.get_formatter("csv")(42)
    assert _parse_csv(rendered) == [["42"]]


def test_csv_empty_list():
    assert formatters.get_formatter("csv")([]) == ""


def test_csv_none_cell_renders_empty():
    rendered = formatters.get_formatter("csv")([{"a": None, "b": 2}])
    rows = _parse_csv(rendered)
    assert rows[1] == ["", "2"]


def test_csv_quotes_values_with_commas():
    rendered = formatters.get_formatter("csv")([{"a": "x,y"}])
    rows = _parse_csv(rendered)
    assert rows[1] == ["x,y"]  # round-trips through csv quoting


def test_register_decorator_adds_entry():
    @formatters.register("temp-fmt")
    def _fmt(data):  # pragma: no cover - exercised below
        return "ok"

    try:
        assert formatters.get_formatter("temp-fmt")(None) == "ok"
    finally:
        formatters.REGISTRY.pop("temp-fmt", None)
