import io

import pytest
import typer
from i2g_admin import runtime
from i2g_admin.errors import ApiError, CliError


def test_current_profile_none_outside_command():
    # No active click context → no profile.
    assert runtime.current_profile() is None


def test_load_data_bare_at_sign_errors():
    with pytest.raises(CliError) as exc:
        runtime._load_data("@")
    assert "requires a filename" in str(exc.value)


def test_load_data_inline_and_stdin(monkeypatch):
    assert runtime._load_data('{"a": 1}') == {"a": 1}
    monkeypatch.setattr("sys.stdin", io.StringIO('{"c": 3}'))
    assert runtime._load_data("@-") == {"c": 3}


def test_execute_skips_emit_for_none(capsys):
    runtime._execute(lambda: None)
    assert capsys.readouterr().out == ""


def test_execute_maps_cli_error_to_exit():
    with pytest.raises(typer.Exit):
        runtime._execute(lambda: (_ for _ in ()).throw(ApiError(400, "nope")))


def test_execute_debug_emits_repr(monkeypatch, capsys):
    # With an active context that has debug=True, the error repr is also printed.
    from i2g_admin.context import Context

    class FakeCtx:
        obj = Context(debug=True)

    monkeypatch.setattr(runtime, "_current_context", lambda: FakeCtx.obj)

    def boom():
        raise CliError("boom message")

    with pytest.raises(typer.Exit):
        runtime._execute(boom)
    err = capsys.readouterr().err
    assert "boom message" in err
    assert "CliError" in err  # repr() includes the class name
