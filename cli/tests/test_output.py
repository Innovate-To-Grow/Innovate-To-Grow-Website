import json

from i2g_admin.output import emit


def test_emit_json(capsys):
    emit({"a": 1}, as_json=True)
    assert json.loads(capsys.readouterr().out) == {"a": 1}


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
