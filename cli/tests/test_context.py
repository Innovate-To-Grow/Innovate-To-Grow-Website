from i2g_admin import context as ctxmod
from i2g_admin.client import ApiClient
from i2g_admin.context import Context, build_client


def test_build_client_uses_profile_and_timeouts(monkeypatch):
    captured = {}

    def fake_ensure(profile=None):
        captured["profile"] = profile
        return "https://b", "TOK"

    monkeypatch.setattr(ctxmod.auth, "ensure_token", fake_ensure)
    context = Context(profile="staging", connect_timeout=2.0, read_timeout=4.0, max_attempts=3)
    client = build_client(context)
    assert isinstance(client, ApiClient)
    assert captured["profile"] == "staging"
    assert client.timeout == (2.0, 4.0)
    assert client.max_attempts == 3
