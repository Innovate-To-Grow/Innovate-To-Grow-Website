"""Tests for the app glue helpers: _client, _execute, _load_data."""

import io

import pytest
import typer
from i2g_admin import app as appmod
from i2g_admin.core.errors import ApiError, CliError


def test_client_builds_api_client(monkeypatch):
    monkeypatch.setattr(appmod.auth, "ensure_token", lambda: ("https://b", "TOK"))
    client = appmod._client()
    assert client.base_url == "https://b"


def test_execute_skips_emit_for_none(capsys):
    appmod._execute(lambda: None, as_json=False)
    assert capsys.readouterr().out == ""


def test_execute_maps_cli_error_to_exit():
    def boom():
        raise ApiError(400, "nope")

    with pytest.raises(typer.Exit):
        appmod._execute(boom)


def test_load_data_inline():
    assert appmod._load_data('{"a": 1}') == {"a": 1}


def test_load_data_from_file(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text('{"b": 2}')
    assert appmod._load_data(f"@{path}") == {"b": 2}


def test_load_data_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"c": 3}'))
    assert appmod._load_data("@-") == {"c": 3}


def test_load_data_invalid_json_raises():
    with pytest.raises(CliError):
        appmod._load_data("{not json")
