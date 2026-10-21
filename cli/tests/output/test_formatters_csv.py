"""csv / csv-raw formatters, including spreadsheet-formula neutralization."""

import csv
import io

import pytest
from i2g_admin.output import formatters


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


@pytest.mark.parametrize(
    "dangerous",
    [
        '=HYPERLINK("https://attacker.example")',
        "+1+1",
        "-2+3",
        "@SUM(A1:A2)",
        "  =1+1",
        "\t=1+1",
        "\r=1+1",
    ],
)
def test_csv_neutralizes_spreadsheet_formulas(dangerous):
    rendered = formatters.get_formatter("csv")([{"value": dangerous}])
    assert _parse_csv(rendered)[1][0] == f"'{dangerous}"


def test_csv_raw_preserves_formula_for_machine_consumers():
    rendered = formatters.get_formatter("csv-raw")([{"value": "=1+1"}])
    assert _parse_csv(rendered)[1][0] == "=1+1"
