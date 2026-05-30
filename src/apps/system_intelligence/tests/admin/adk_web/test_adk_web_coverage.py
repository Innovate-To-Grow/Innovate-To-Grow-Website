"""Line-coverage tests for the system_intelligence adk_web batch.

Every test below targets specific uncovered lines reported by coverage and
asserts the resulting behaviour (return value, status code, rewritten scope,
emitted ASGI messages, or DB-backed session lookup result). All heavy ADK /
FastAPI machinery is exercised through the in-process ASGI interface; no
network or real LLM calls are made.
"""

import asyncio
import importlib.metadata
import json
from http import cookies
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

import apps.system_intelligence.admin.adk_web.bridge as bridge_module
from apps.event.tests.helpers import make_member, make_superuser
from apps.system_intelligence.admin.adk_web import (
    AdminADKWebAuthMiddleware,
    SystemIntelligenceADKRouter,
    load_staff_user_id_from_headers,
)
from apps.system_intelligence.admin.adk_web.app import (
    _google_adk_version,
    _json_file_matches,
    get_protected_system_intelligence_adk_asgi_application,
    get_system_intelligence_adk_asgi_application,
)
from apps.system_intelligence.admin.adk_web.auth.responses import _send_redirect_to_admin_login
from apps.system_intelligence.admin.adk_web.auth.rewrite import (
    _read_body,
    _rewrite_json_body_user_id,
    _rewrite_query_user_id,
    _rewrite_scope_user_id,
    _scope_adk_path,
)
from apps.system_intelligence.admin.adk_web.auth.session import (
    _load_staff_user_id_from_headers_sync,
    _session_key_from_headers,
)
from apps.system_intelligence.admin.adk_web.bridge import _get_bridge_app, _server_port, adk_http_view
from apps.system_intelligence.admin.adk_web.constants import SYSTEM_INTELLIGENCE_ADK_PREFIX
from apps.system_intelligence.services.adk.constants import APP_NAME

from .adk_web_helpers import RecorderApp, invoke_http, invoke_websocket, read_test_body

PREFIX = SYSTEM_INTELLIGENCE_ADK_PREFIX


# ---------------------------------------------------------------------------
# session.py — Django session loading from raw ASGI cookie headers.
# ---------------------------------------------------------------------------
class SessionLoadingTests(TestCase):
    """Covers session.py lines 14, 18-45, 49-58."""

    def setUp(self):
        # _load_staff_user_id_from_headers_sync calls close_old_connections()
        # (it normally runs in a sync_to_async worker thread). Called directly
        # inside the TestCase transaction it would close the test's own
        # connection — harmless on SQLite but raises InterfaceError on
        # PostgreSQL. Neutralize the connection teardown for these direct calls.
        patcher = mock.patch("apps.system_intelligence.admin.adk_web.auth.session.close_old_connections")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cookie_headers_for(self, member):
        """Log the member in through the test client and return ASGI headers.

        The DB-backed cases call ``_load_staff_user_id_from_headers_sync``
        directly (synchronously, on the test thread and inside the test
        transaction) to avoid SQLite cross-thread lock contention that the
        ``sync_to_async`` wrapper would otherwise introduce. The async wrapper
        itself is exercised by ``test_async_wrapper_returns_none_without_db``.
        """
        self.client.force_login(member)
        session_key = self.client.cookies["sessionid"].value
        return [(b"cookie", f"sessionid={session_key}".encode())]

    def test_async_wrapper_returns_none_without_db(self):
        # Exercises the public async entrypoint (line 14). No cookie header
        # means the sync helper returns before any DB access.
        result = asyncio.run(load_staff_user_id_from_headers([(b"accept", b"*/*")]))

        self.assertIsNone(result)

    def test_sync_loader_returns_pk_for_active_staff_session(self):
        admin = make_superuser()
        headers = self._cookie_headers_for(admin)

        result = _load_staff_user_id_from_headers_sync(headers)

        self.assertEqual(result, str(admin.pk))

    def test_sync_loader_returns_none_without_cookie_header(self):
        # No cookie header -> _session_key_from_headers returns None (line 21-22).
        result = _load_staff_user_id_from_headers_sync([(b"accept", b"*/*")])

        self.assertIsNone(result)

    def test_sync_loader_returns_none_for_unknown_session_key(self):
        # Valid cookie shape but the session row has no SESSION_KEY (line 27-28).
        result = _load_staff_user_id_from_headers_sync([(b"cookie", b"sessionid=does-not-exist")])

        self.assertIsNone(result)

    def test_sync_loader_returns_none_when_user_missing(self):
        admin = make_superuser()
        headers = self._cookie_headers_for(admin)
        # Delete the user so .get(pk=...) raises DoesNotExist (line 32-33).
        admin.delete()

        result = _load_staff_user_id_from_headers_sync(headers)

        self.assertIsNone(result)

    def test_sync_loader_rejects_non_staff_user(self):
        member = make_member(email="user@example.com")
        self.assertFalse(member.is_staff)
        headers = self._cookie_headers_for(member)

        result = _load_staff_user_id_from_headers_sync(headers)

        self.assertIsNone(result)

    def test_sync_loader_rejects_inactive_user(self):
        admin = make_superuser()
        headers = self._cookie_headers_for(admin)
        admin.is_active = False
        admin.save(update_fields=["is_active"])

        result = _load_staff_user_id_from_headers_sync(headers)

        self.assertIsNone(result)

    def test_sync_loader_rejects_tampered_session_hash(self):
        admin = make_superuser()
        headers = self._cookie_headers_for(admin)
        # Rotate the password so the stored session auth hash no longer matches
        # (constant_time_compare fails -> line 41).
        admin.set_password("a-brand-new-password")
        admin.save(update_fields=["password"])

        result = _load_staff_user_id_from_headers_sync(headers)

        self.assertIsNone(result)

    def test_session_key_from_headers_returns_none_when_load_raises_cookie_error(self):
        # CookieError path (lines 53-56). Python's SimpleCookie.load() is lenient
        # and silently drops malformed morsels, so the defensive handler is only
        # reachable by forcing load() to raise; patch the http.cookies reference
        # the source module actually uses.
        class _RaisingCookie(cookies.SimpleCookie):
            def load(self, rawdata):
                raise cookies.CookieError("boom")

        with mock.patch(
            "apps.system_intelligence.admin.adk_web.auth.session.cookies.SimpleCookie",
            _RaisingCookie,
        ):
            result = _session_key_from_headers([(b"cookie", b"sessionid=abc")])

        self.assertIsNone(result)

    def test_session_key_from_headers_returns_none_when_cookie_lacks_session(self):
        # Parses fine but has no sessionid morsel (line 57-58 -> None).
        result = _session_key_from_headers([(b"cookie", b"other=value")])

        self.assertIsNone(result)

    def test_session_key_from_headers_extracts_value(self):
        result = _session_key_from_headers([(b"cookie", b"sessionid=abc123; other=x")])

        self.assertEqual(result, "abc123")


# ---------------------------------------------------------------------------
# middleware.py — non-http passthrough + anonymous websocket close.
# ---------------------------------------------------------------------------
class MiddlewarePassthroughTests(SimpleTestCase):
    """Covers middleware.py lines 17-18 and 24."""

    def test_lifespan_scope_passes_through_untouched(self):
        recorder = RecorderApp()
        app = AdminADKWebAuthMiddleware(recorder, user_loader=_fail_loader)

        async def receive():
            return {"type": "lifespan.startup"}

        async def send(_message):
            return None

        asyncio.run(app({"type": "lifespan"}, receive, send))

        # The inner app received the lifespan scope without auth handling.
        self.assertEqual(recorder.scope["type"], "lifespan")

    def test_anonymous_websocket_is_closed_with_policy_violation(self):
        app = AdminADKWebAuthMiddleware(RecorderApp(), user_loader=_no_user)

        messages = asyncio.run(invoke_websocket(app, {"path": "/run_live"}))

        self.assertEqual(messages, [{"type": "websocket.close", "code": 1008}])


# ---------------------------------------------------------------------------
# responses.py — redirect appends the original query string.
# ---------------------------------------------------------------------------
class RedirectResponseTests(SimpleTestCase):
    """Covers responses.py line 9."""

    def test_redirect_preserves_query_string_in_next_param(self):
        scope = {
            "type": "http",
            "adk_original_path": "/admin/system-intelligence/adk/dev-ui/",
            "query_string": b"foo=bar&baz=1",
        }
        messages = []

        async def send(message):
            messages.append(message)

        asyncio.run(_send_redirect_to_admin_login(scope, send))

        location = dict(messages[0]["headers"])[b"location"].decode("latin1")
        self.assertEqual(messages[0]["status"], 302)
        # quote() keeps ?, =, & in the safe set, so the query is carried through verbatim.
        self.assertEqual(location, "/admin/login/?next=/admin/system-intelligence/adk/dev-ui/?foo=bar&baz=1")


# ---------------------------------------------------------------------------
# router.py — lifespan handling + websocket close for unmatched paths.
# ---------------------------------------------------------------------------
class RouterLifespanTests(SimpleTestCase):
    """Covers router.py lines 14-15, 25-29, 37-43."""

    def test_lifespan_startup_and_shutdown_are_completed(self):
        app = SystemIntelligenceADKRouter(RecorderApp(), RecorderApp())
        sent = []
        incoming = iter(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        )

        async def receive():
            return next(incoming)

        async def send(message):
            sent.append(message)

        asyncio.run(app({"type": "lifespan"}, receive, send))

        self.assertEqual(
            sent,
            [
                {"type": "lifespan.startup.complete"},
                {"type": "lifespan.shutdown.complete"},
            ],
        )

    def test_non_prefixed_http_falls_through_to_django(self):
        django_app = RecorderApp()
        adk_app = RecorderApp()
        app = SystemIntelligenceADKRouter(django_app, adk_app)

        messages = asyncio.run(invoke_http(app, {"path": "/admin/other/"}))

        self.assertEqual(messages[0]["status"], 204)
        self.assertEqual(django_app.scope["path"], "/admin/other/")
        self.assertIsNone(adk_app.scope)

    def test_non_prefixed_websocket_is_closed(self):
        django_app = RecorderApp()
        adk_app = RecorderApp()
        app = SystemIntelligenceADKRouter(django_app, adk_app)

        messages = asyncio.run(invoke_websocket(app, {"path": "/ws/other"}))

        self.assertEqual(messages, [{"type": "websocket.close", "code": 1008}])
        self.assertIsNone(django_app.scope)
        self.assertIsNone(adk_app.scope)


# ---------------------------------------------------------------------------
# rewrite.py — scope/path/body user-id rewriting edge cases.
# ---------------------------------------------------------------------------
class RewriteHelperTests(SimpleTestCase):
    """Covers rewrite.py lines 17, 30, 51, 59-60, 68, 77, 87."""

    def test_scope_rewrite_updates_raw_path_when_present(self):
        scope = {
            "type": "http",
            "path": f"{PREFIX}/apps/{APP_NAME}/users/user/sessions",
            "raw_path": f"{PREFIX}/apps/{APP_NAME}/users/user/sessions".encode("latin1"),
            "root_path": PREFIX,
        }

        rewritten = _rewrite_scope_user_id(scope, "admin-7")

        self.assertEqual(
            rewritten["raw_path"].decode("latin1"),
            f"{PREFIX}/apps/{APP_NAME}/users/admin-7/sessions",
        )

    def test_scope_adk_path_returns_slash_when_path_equals_root(self):
        # Line 30: path == root_path -> "/".
        result = _scope_adk_path({"path": PREFIX, "root_path": PREFIX})

        self.assertEqual(result, "/")

    def test_run_live_query_appends_user_id_when_absent(self):
        scope = {
            "type": "websocket",
            "path": f"{PREFIX}/run_live",
            "root_path": PREFIX,
            "query_string": b"app_name=demo&session_id=s1",
        }

        rewritten = _rewrite_scope_user_id(scope, "admin-9")

        # replaced stays False so user_id is appended (line 51).
        self.assertIn(b"user_id=admin-9", rewritten["query_string"])

    def test_rewrite_query_user_id_replaces_existing_value(self):
        result = _rewrite_query_user_id(b"user_id=old&x=1", "admin-3")

        self.assertEqual(result, b"user_id=admin-3&x=1")

    def test_json_body_rewrite_leaves_invalid_json_untouched(self):
        # Lines 59-60: JSONDecodeError -> new_body = original body.
        scope = {"headers": [(b"content-type", b"application/json")]}
        raw = b"not-json-at-all"

        replay = asyncio.run(_rewrite_json_body_user_id(scope, _single_body_receive(raw), "admin-1"))
        body = asyncio.run(read_test_body(replay))

        self.assertEqual(body, raw)
        # content-length header is NOT touched because the body was unchanged.
        self.assertEqual(scope["headers"], [(b"content-type", b"application/json")])

    def test_json_body_rewrite_leaves_non_dict_payload_untouched(self):
        # Line 68: payload parses but is a list, not a dict.
        scope = {"headers": []}
        raw = b"[1, 2, 3]"

        replay = asyncio.run(_rewrite_json_body_user_id(scope, _single_body_receive(raw), "admin-1"))
        body = asyncio.run(read_test_body(replay))

        self.assertEqual(body, raw)

    def test_json_body_rewrite_injects_user_id_into_dict(self):
        scope = {"headers": []}
        raw = json.dumps({"user_id": "old"}).encode()

        replay = asyncio.run(_rewrite_json_body_user_id(scope, _single_body_receive(raw), "admin-5"))
        body = asyncio.run(read_test_body(replay))

        payload = json.loads(body.decode())
        self.assertEqual(payload["user_id"], "admin-5")
        self.assertEqual(payload["userId"], "admin-5")
        self.assertIn((b"content-length", str(len(body)).encode()), scope["headers"])

    def test_replay_receive_delegates_after_first_call(self):
        # Line 77: second invocation of replay_receive falls through to the
        # underlying receive (which here yields a disconnect).
        scope = {"headers": []}
        raw = json.dumps({"user_id": "old"}).encode()

        async def driver():
            disconnect = {"type": "http.disconnect"}
            calls = iter([{"type": "http.request", "body": raw, "more_body": False}, disconnect])

            async def receive():
                return next(calls)

            replay = await _rewrite_json_body_user_id(scope, receive, "admin-2")
            first = await replay()
            second = await replay()
            return first, second

        first, second = asyncio.run(driver())

        self.assertEqual(first["type"], "http.request")
        self.assertEqual(second, {"type": "http.disconnect"})

    def test_read_body_breaks_on_disconnect(self):
        # Line 87: http.disconnect terminates the read loop.
        async def receive():
            return {"type": "http.disconnect"}

        body = asyncio.run(_read_body(receive))

        self.assertEqual(body, b"")

    def test_read_body_concatenates_multi_part_request(self):
        chunks = iter(
            [
                {"type": "http.request", "body": b"hello ", "more_body": True},
                {"type": "http.request", "body": b"world", "more_body": False},
            ]
        )

        async def receive():
            return next(chunks)

        body = asyncio.run(_read_body(receive))

        self.assertEqual(body, b"hello world")


# ---------------------------------------------------------------------------
# bridge.py — disconnect after body, lazy app init, port parsing.
# ---------------------------------------------------------------------------
class BridgeTests(SimpleTestCase):
    """Covers bridge.py lines 42, 55-57, 98-99."""

    def test_call_adk_app_returns_disconnect_after_body_consumed(self):
        captured = {}

        class _App:
            async def __call__(self, scope, receive, send):
                first = await receive()
                second = await receive()
                captured["first"] = first
                captured["second"] = second
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ok"})

        request = RequestFactory().generic(
            "POST",
            f"{PREFIX}/run_sse",
            data=b'{"x":1}',
            content_type="application/json",
        )

        with mock.patch(
            "apps.system_intelligence.admin.adk_web.bridge._get_bridge_app",
            return_value=_App(),
        ):
            response = adk_http_view(request, "run_sse")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["first"]["body"], b'{"x":1}')
        # Second receive after body is sent yields a disconnect (line 42).
        self.assertEqual(captured["second"], {"type": "http.disconnect"})

    def test_get_bridge_app_initialises_once_and_caches(self):
        sentinel = object()
        original = bridge_module._BRIDGE_APP
        bridge_module._BRIDGE_APP = None
        try:
            with mock.patch(
                "apps.system_intelligence.admin.adk_web.bridge.get_protected_system_intelligence_adk_asgi_application",
                return_value=sentinel,
            ) as factory:
                first = _get_bridge_app()
                second = _get_bridge_app()
        finally:
            bridge_module._BRIDGE_APP = original

        self.assertIs(first, sentinel)
        self.assertIs(second, sentinel)
        factory.assert_called_once()

    def test_server_port_falls_back_to_eighty_on_invalid_port(self):
        request = RequestFactory().get("/")
        request.META["SERVER_PORT"] = "not-a-number"

        self.assertEqual(_server_port(request), 80)

    def test_server_port_parses_numeric_port(self):
        request = RequestFactory().get("/")
        request.META["SERVER_PORT"] = "8000"

        self.assertEqual(_server_port(request), 8000)


# ---------------------------------------------------------------------------
# app.py — FastAPI route handlers + asset helpers.
# ---------------------------------------------------------------------------
class AppRouteTests(SimpleTestCase):
    """Covers app.py lines 55, 62-64, 74-76, 80-82, 86, 90, 103, 173-174, 181-182."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp = TemporaryDirectory()
        base_dir = Path(cls._temp.name) / "app"
        cls._override = override_settings(BASE_DIR=base_dir, MEDIA_ROOT=base_dir / "media")
        cls._override.enable()
        cls.app = get_system_intelligence_adk_asgi_application()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        cls._temp.cleanup()
        super().tearDownClass()

    def _get(self, sub_path):
        return asyncio.run(invoke_http(self.app, {"path": PREFIX + sub_path, "root_path": PREFIX}))

    @staticmethod
    def _body(messages):
        return b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")

    def test_dev_ui_config_returns_logo_metadata(self):
        # Line 55.
        messages = self._get("/dev-ui/config")
        payload = json.loads(self._body(messages))

        self.assertEqual(messages[0]["status"], 200)
        self.assertEqual(payload["logo_text"], "System Intelligence")
        self.assertTrue(payload["logo_image_url"].endswith("ADK-512-color.svg"))

    def test_build_graph_returns_agent_metadata_for_known_app(self):
        # Lines 64-70 (success branch reached via the matching app name).
        messages = self._get(f"/dev/build_graph/{APP_NAME}")
        payload = json.loads(self._body(messages))

        self.assertEqual(messages[0]["status"], 200)
        self.assertEqual(payload["name"], APP_NAME)
        self.assertEqual(payload["root_agent"]["name"], "system_intelligence")

    def test_build_graph_returns_404_for_unknown_app(self):
        # Lines 62-63.
        messages = self._get("/dev/build_graph/unknown-app")

        self.assertEqual(messages[0]["status"], 404)

    def test_build_graph_image_returns_204_for_known_app(self):
        # Line 76.
        messages = self._get(f"/dev/build_graph_image/{APP_NAME}")

        self.assertEqual(messages[0]["status"], 204)

    def test_build_graph_image_returns_404_for_unknown_app(self):
        # Lines 74-75.
        messages = self._get("/dev/build_graph_image/unknown-app")

        self.assertEqual(messages[0]["status"], 404)

    def test_agent_builder_returns_empty_for_known_app(self):
        # Line 82.
        messages = self._get(f"/builder/app/{APP_NAME}")

        self.assertEqual(messages[0]["status"], 200)
        self.assertEqual(self._body(messages), b"")

    def test_agent_builder_returns_404_for_unknown_app(self):
        # Lines 80-81.
        messages = self._get("/builder/app/unknown-app")

        self.assertEqual(messages[0]["status"], 404)

    def test_root_redirects_to_dev_ui(self):
        # Line 86.
        messages = self._get("/")

        self.assertIn(messages[0]["status"], (302, 307))
        location = dict(messages[0]["headers"])[b"location"].decode("latin1")
        self.assertTrue(location.endswith("/dev-ui/"))

    def test_dev_ui_without_slash_redirects_to_dev_ui(self):
        # Line 90.
        messages = self._get("/dev-ui")

        self.assertIn(messages[0]["status"], (302, 307))
        location = dict(messages[0]["headers"])[b"location"].decode("latin1")
        self.assertTrue(location.endswith("/dev-ui/"))

    def test_protected_application_wraps_app_in_auth_middleware(self):
        # Line 103.
        protected = get_protected_system_intelligence_adk_asgi_application()

        self.assertIsInstance(protected, AdminADKWebAuthMiddleware)


class AppAssetHelperTests(SimpleTestCase):
    """Covers app.py lines 173-174 and 181-182 directly."""

    def test_google_adk_version_returns_unknown_when_package_missing(self):
        with mock.patch(
            "apps.system_intelligence.admin.adk_web.app.package_version",
            side_effect=importlib.metadata.PackageNotFoundError("google-adk"),
        ):
            self.assertEqual(_google_adk_version(), "unknown")

    def test_google_adk_version_returns_installed_version(self):
        with mock.patch(
            "apps.system_intelligence.admin.adk_web.app.package_version",
            return_value="9.9.9",
        ):
            self.assertEqual(_google_adk_version(), "9.9.9")

    def test_json_file_matches_returns_false_for_missing_file(self):
        # OSError branch (lines 181-182).
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "absent.json"

            self.assertFalse(_json_file_matches(missing, {"a": 1}))

    def test_json_file_matches_returns_false_for_invalid_json(self):
        # JSONDecodeError branch (lines 181-182).
        with TemporaryDirectory() as temp_dir:
            broken = Path(temp_dir) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")

            self.assertFalse(_json_file_matches(broken, {"a": 1}))

    def test_json_file_matches_returns_true_for_equal_payload(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "match.json"
            path.write_text(json.dumps({"a": 1}), encoding="utf-8")

            self.assertTrue(_json_file_matches(path, {"a": 1}))


# ---------------------------------------------------------------------------
# Shared async stand-ins.
# ---------------------------------------------------------------------------
async def _no_user(_headers):
    return None


async def _fail_loader(_headers):  # pragma: no cover - must never be awaited
    raise AssertionError("user_loader must not run for non-http/websocket scopes")


def _single_body_receive(body: bytes):
    state = {"sent": False}

    async def receive():
        if state["sent"]:
            return {"type": "http.disconnect"}
        state["sent"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive
