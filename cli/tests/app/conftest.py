import pytest
from i2g_admin.core import runtime
from typer.testing import CliRunner

runner = CliRunner()


class FakeClient:
    def __init__(self, **canned):
        self.canned = canned
        self.calls = []

    def _record(self, method, path, kwargs):
        self.calls.append((method, path, kwargs))
        result = self.canned.get(method.lower())
        if isinstance(result, dict) and path in result:
            return result[path]
        return result

    def get(self, path, **kwargs):
        return self._record("GET", path, kwargs)

    def post(self, path, **kwargs):
        return self._record("POST", path, kwargs)

    def patch(self, path, **kwargs):
        return self._record("PATCH", path, kwargs)

    def delete(self, path, **kwargs):
        return self._record("DELETE", path, kwargs)


@pytest.fixture
def use_client(monkeypatch):
    """Install a fake API client as the command-layer client factory.

    ``use_client(get={...}, post={...})`` builds a :class:`FakeClient`;
    ``use_client(custom)`` installs an already-constructed client object.
    """

    def install(client=None, **canned):
        if client is None:
            client = FakeClient(**canned)
        # Command modules resolve the glue from i2g_admin.core.runtime; patch it there.
        monkeypatch.setattr(runtime, "_client", lambda: client)
        return client

    return install
