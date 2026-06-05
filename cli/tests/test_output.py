import json

import pytest

from i2g_admin.errors import CliError
from i2g_admin.output import emit


def test_emit_json(capsys):
    emit({"a": 1}, as_json=True)
    assert json.loads(capsys.readouterr().out) == {"a": 1}


# --- format-selection precedence (regression guard for the fmt ternary) -----
def test_as_json_overrides_table_output(capsys):
    """--json wins over an explicit --output table; output is valid JSON."""
    emit({"a": 1}, as_json=True, output="table")
    assert json.loads(capsys.readouterr().out) == {"a": 1}


def test_as_json_overrides_yaml_output(capsys):
    """--json takes precedence over --output yaml (the documented contract)."""
    emit({"a": 1}, as_json=True, output="yaml")
    assert json.loads(capsys.readouterr().out) == {"a": 1}


def test_output_yaml_selected_when_not_json(capsys):
    emit({"a": 1}, output="yaml")
    assert capsys.readouterr().out.strip() == "a: 1"


def test_output_csv_selected_when_not_json(capsys):
    emit({"a": 1}, output="csv")
    out = capsys.readouterr().out
    assert "key,value" in out
    assert "a,1" in out


def test_output_defaults_to_table(capsys):
    """No as_json and no output → the rich table renderer, without raising."""
    emit({"key": "value"})
    assert "key" in capsys.readouterr().out


def test_unknown_output_format_raises_cli_error():
    with pytest.raises(CliError) as exc:
        emit({"a": 1}, output="nonsense")
    assert "Unknown output format" in str(exc.value)
    assert "'nonsense'" in str(exc.value)


def test_emit_list_of_dicts(capsys):
    emit([{"x": 1, "y": 2}], as_json=False)
    assert "x" in capsys.readouterr().out


def test_emit_empty_list(capsys):
    emit([], as_json=False)
    assert "no results" in capsys.readouterr().out


def test_emit_list_of_scalars(capsys):
    emit(["alpha", "beta"], as_json=False)
    assert "alpha" in capsys.readouterr().out


def test_emit_dict(capsys):
    emit({"key": "value"}, as_json=False)
    assert "key" in capsys.readouterr().out


def test_emit_scalar(capsys):
    emit("hello world", as_json=False)
    assert "hello" in capsys.readouterr().out
