import json

import pytest
from i2g_admin import runtime
from i2g_admin.app import app
from i2g_admin.commands.skeleton import build_skeleton
from typer.testing import CliRunner

runner = CliRunner()


class FakeClient:
    def __init__(self, **canned):
        self.canned = canned
        self.calls = []

    def _record(self, method, path, kwargs):
        self.calls.append((method, path, kwargs))
        return self.canned.get(method.lower())

    def get(self, path, **kwargs):
        return self._record("GET", path, kwargs)

    def post(self, path, **kwargs):
        return self._record("POST", path, kwargs)

    def patch(self, path, **kwargs):
        return self._record("PATCH", path, kwargs)


@pytest.fixture
def use_client(monkeypatch):
    def install(client):
        monkeypatch.setattr(runtime, "_client", lambda: client)
        return client

    return install


# ---- build_skeleton -------------------------------------------------------
def test_build_skeleton_covers_each_type():
    schema = {
        "writable_fields": [
            {"name": "title", "type": "CharField"},
            {"name": "body", "type": "TextField"},
            {"name": "slug", "type": "SlugField"},
            {"name": "email", "type": "EmailField"},
            {"name": "url", "type": "URLField"},
            {"name": "ip", "type": "GenericIPAddressField"},
            {"name": "uid", "type": "UUIDField"},
            {"name": "starts_on", "type": "DateField"},
            {"name": "created_at", "type": "DateTimeField"},
            {"name": "count", "type": "IntegerField"},
            {"name": "votes", "type": "PositiveIntegerField"},
            {"name": "owner_id", "type": "ForeignKey"},
            {"name": "profile_id", "type": "OneToOneField"},
            {"name": "ratio", "type": "FloatField"},
            {"name": "price", "type": "DecimalField"},
            {"name": "active", "type": "BooleanField"},
            {"name": "tags", "type": "ManyToManyField"},
            {"name": "meta", "type": "JSONField"},
            {"name": "weird", "type": "SomeUnknownField"},
        ]
    }
    assert build_skeleton(schema) == {
        "title": "",
        "body": "",
        "slug": "",
        "email": "",
        "url": "",
        "ip": "",
        "uid": "",
        "starts_on": "",
        "created_at": "",
        "count": 0,
        "votes": 0,
        "owner_id": 0,
        "profile_id": 0,
        "ratio": 0.0,
        "price": 0.0,
        "active": False,
        "tags": [],
        "meta": {},
        "weird": None,
    }


def test_build_skeleton_empty_schema():
    assert build_skeleton({}) == {}
    assert build_skeleton({"writable_fields": []}) == {}


def test_build_skeleton_skips_field_without_name():
    schema = {"writable_fields": [{"type": "CharField"}, {"name": "ok", "type": "CharField"}]}
    assert build_skeleton(schema) == {"ok": ""}


# ---- --generate-cli-skeleton ----------------------------------------------
def test_create_generate_skeleton_prints_template_and_skips_post(use_client):
    client = use_client(
        FakeClient(
            get={
                "model": "projects.Semester",
                "writable_fields": [
                    {"name": "year", "type": "IntegerField"},
                    {"name": "label", "type": "CharField"},
                ],
            }
        )
    )
    result = runner.invoke(app, ["records", "create", "projects", "semester", "--generate-cli-skeleton"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"year": 0, "label": ""}
    # Only the schema GET happened; no POST.
    assert [call[0] for call in client.calls] == ["GET"]
    assert client.calls[0][1] == "/admin-api/models/projects/semester/schema/"


def test_update_generate_skeleton_prints_template_and_skips_patch(use_client):
    client = use_client(
        FakeClient(get={"model": "projects.Semester", "writable_fields": [{"name": "label", "type": "CharField"}]})
    )
    result = runner.invoke(app, ["records", "update", "projects", "semester", "abc", "--generate-cli-skeleton"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"label": ""}
    assert [call[0] for call in client.calls] == ["GET"]


# ---- --cli-input-json -----------------------------------------------------
def test_create_with_cli_input_json_inline(use_client):
    client = use_client(FakeClient(post={"id": "new"}))
    result = runner.invoke(
        app,
        ["records", "create", "projects", "semester", "--cli-input-json", '{"year": 2026, "season": 1}'],
    )
    assert result.exit_code == 0
    assert client.calls[0][0] == "POST"
    assert client.calls[0][2]["json_body"] == {"year": 2026, "season": 1}


def test_create_with_cli_input_json_file(use_client, tmp_path):
    client = use_client(FakeClient(post={"id": "new"}))
    payload = tmp_path / "payload.json"
    payload.write_text('{"year": 2027}')
    result = runner.invoke(
        app,
        ["records", "create", "projects", "semester", "--cli-input-json", f"@{payload}"],
    )
    assert result.exit_code == 0
    assert client.calls[0][2]["json_body"] == {"year": 2027}


def test_update_with_cli_input_json_inline(use_client):
    client = use_client(FakeClient(patch={"id": "abc"}))
    result = runner.invoke(
        app,
        ["records", "update", "projects", "semester", "abc", "--cli-input-json", '{"is_published": true}'],
    )
    assert result.exit_code == 0
    assert client.calls[0][0] == "PATCH"
    assert client.calls[0][2]["json_body"] == {"is_published": True}


# ---- conflicting / missing input ------------------------------------------
def test_create_missing_input_errors(use_client):
    use_client(FakeClient(post={"id": "new"}))
    result = runner.invoke(app, ["records", "create", "projects", "semester"])
    assert result.exit_code == 1
    assert "--data or --cli-input-json" in result.output


def test_create_conflicting_input_errors(use_client):
    use_client(FakeClient(post={"id": "new"}))
    result = runner.invoke(
        app,
        ["records", "create", "projects", "semester", "--data", "{}", "--cli-input-json", "{}"],
    )
    assert result.exit_code == 1
    assert "only one of --data or --cli-input-json" in result.output


def test_update_missing_input_errors(use_client):
    use_client(FakeClient(patch={"id": "abc"}))
    result = runner.invoke(app, ["records", "update", "projects", "semester", "abc"])
    assert result.exit_code == 1
    assert "--data or --cli-input-json" in result.output


def test_update_conflicting_input_errors(use_client):
    use_client(FakeClient(patch={"id": "abc"}))
    result = runner.invoke(
        app,
        ["records", "update", "projects", "semester", "abc", "--data", "{}", "--cli-input-json", "{}"],
    )
    assert result.exit_code == 1
    assert "only one of --data or --cli-input-json" in result.output
