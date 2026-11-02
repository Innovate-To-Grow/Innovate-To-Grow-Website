"""Scope classification order: preflight, exemptions, the view's own scope, app registrations, the route table,
then the path / method / sign-in fallback."""

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from apps.core.services.request_limits import register_exemption, register_scope, scopes

from .helpers import isolate, limits_with
from .urls import MethodScopedView, exempt_view, unscoped

TEST_URLS = "apps.core.tests.request_limits.urls"


def resolved(factory_method, path, **extra):
    request = factory_method(path, **extra)
    request.resolver_match = resolve(path)
    return request, request.resolver_match.func


@override_settings(ROOT_URLCONF=TEST_URLS, REQUEST_RATE_LIMITS=limits_with())
class ClassifyTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.factory = RequestFactory()

    def classify(self, method, path, **extra):
        request, view = resolved(getattr(self.factory, method.lower()), path, **extra)
        return scopes.classify(request, view)

    def test_preflight_is_exempt(self):
        found = self.classify("OPTIONS", "/p3/")
        self.assertEqual((found.scope, found.exempt, found.source), (None, scopes.PREFLIGHT, "preflight"))

    def test_the_view_attribute_names_the_scope(self):
        self.assertEqual(self.classify("GET", "/p3/"), scopes.Classification("t-p3", None, "view"))

    def test_a_method_map_on_a_class_view(self):
        self.assertEqual(self.classify("GET", "/methods/").scope, "t-p1")
        self.assertEqual(self.classify("POST", "/methods/").scope, "t-p3")
        self.assertEqual(scopes.view_path(resolve("/methods/").func), f"{MethodScopedView.__module__}.MethodScopedView")

    def test_view_exemption_attribute(self):
        found = self.classify("GET", "/exempt/")
        self.assertEqual((found.scope, found.exempt, found.source), (None, "Test exemption.", "exempt"))

    def test_registration_and_settings_by_view_name_or_path(self):
        register_scope("unscoped", {"POST": "t-p2"})
        self.assertEqual(self.classify("POST", "/unscoped/"), scopes.Classification("t-p2", None, "registered"))
        # The method map has no GET (nor "*"): the next source decides.
        with self.settings(REQUEST_RATE_LIMITS=limits_with(routes={"unscoped": "t-p0"})):
            self.assertEqual(self.classify("GET", "/unscoped/"), scopes.Classification("t-p0", None, "route"))
        register_exemption(scopes.view_path(unscoped), "Registered reason.")
        self.assertEqual(self.classify("POST", "/unscoped/").exempt, "Registered reason.")

    def test_settings_exemption(self):
        with self.settings(REQUEST_RATE_LIMITS=limits_with(exempt={"unscoped": "Settings reason."})):
            self.assertEqual(self.classify("GET", "/unscoped/").exempt, "Settings reason.")

    def test_an_exemption_needs_a_reason(self):
        with self.assertRaisesMessage(ValueError, "An exemption needs a reason."):
            register_exemption("unscoped", " ")

    def test_registered_returns_copies(self):
        register_scope("a", "t-p1")
        register_exemption("b", "why")
        found, exempt = scopes.registered()
        found["c"] = "x"
        self.assertEqual(scopes.registered(), ({"a": "t-p1"}, {"b": "why"}))
        self.assertEqual(exempt, {"b": "why"})

    def test_fallback_by_method_and_sign_in(self):
        self.assertEqual(self.classify("GET", "/unscoped/"), scopes.Classification("public-read", None, "fallback"))
        self.assertEqual(self.classify("HEAD", "/unscoped/").scope, "public-read")
        self.assertEqual(self.classify("POST", "/unscoped/").scope, "public-write")
        request, view = resolved(self.factory.get, "/unscoped/")
        request._request_limit_identity = scopes.identity.Identity(member="m")
        self.assertEqual(scopes.classify(request, view).scope, "member-read")
        request, view = resolved(self.factory.delete, "/unscoped/")
        request._request_limit_identity = scopes.identity.Identity(user="s")
        self.assertEqual(scopes.classify(request, view).scope, "member-write")

    def test_fallback_by_path(self):
        self.assertEqual(scopes.fallback("/admin-api/records/", "GET", True), "cli")
        self.assertEqual(scopes.fallback("/admin/core/", "POST", True), "staff-admin")
        self.assertEqual(scopes.fallback("/administrator/", "POST", False), "public-write")

    def test_a_request_without_a_resolver_match(self):
        request = self.factory.get("/unscoped/")
        self.assertEqual(scopes.classify(request, unscoped).scope, "public-read")
        request.method = None
        self.assertEqual(scopes.classify(request, exempt_view).exempt, "Test exemption.")

    def test_pick(self):
        self.assertEqual(scopes.pick({"GET": "a", "*": "b"}, "GET"), "a")
        self.assertEqual(scopes.pick({"GET": "a", "*": "b"}, "PUT"), "b")
        self.assertIsNone(scopes.pick({"GET": "a"}, "PUT"))
        self.assertIsNone(scopes.pick("", "GET"))
        self.assertIsNone(scopes.pick(None, "GET"))

    def test_view_path_of_plain_callables(self):
        self.assertEqual(scopes.view_path(unscoped), f"{unscoped.__module__}.unscoped")

        class Callable:
            def __call__(self, request):
                return None

        self.assertTrue(scopes.view_path(Callable()).endswith("Callable"))
