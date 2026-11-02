"""Every route the site serves is limited or exempt with a reason: walk the full URLconf (``get_resolver``) and
classify each route for reads and writes. A new endpoint can therefore never be silently unlimited, a route table
entry can never point at a route that no longer exists, and the user-initiated sign-in and verification routes are
P0."""

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver

from apps.core.services.request_limits import scopes as scope_module
from apps.core.services.request_limits.scopes import classify_route, fallback, view_path

# Only routed with DEBUG on, which the test runner turns off.
DEBUG_ONLY = frozenset({"django.views.static.serve", "django.contrib.staticfiles.views.serve"})
P0_ROUTES = (
    "authn:login",
    "admin-login",
    "authn:email-auth-request-code",
    "authn:phone-auth-request-code",
    "authn:login-request-code",
    "authn:register",
    "authn:password-reset-request-code",
    "authn:password-reset-confirm",
    "authn:login-verify-code",
    "authn:phone-auth-verify-code",
    "event:send-phone-code",
    "event:verify-phone-code",
    "mail:login-link",
    "mail:magic-login",
    "authn:token-refresh",
    "authn:session",
    "authn:send-verification-challenge",
    "event:checkin-scan",
    "mail:ses-events",
)


def _func_path(callback) -> str:
    owner = getattr(callback, "view_class", None) or callback
    module = getattr(owner, "__module__", "")
    return f"{module}.{getattr(owner, '__qualname__', type(owner).__qualname__)}"


def walk(patterns=None, namespaces=(), prefix=""):
    """(route, view_name, callback) for every resolvable route, named as ``ResolverMatch.view_name`` names it."""
    for entry in get_resolver().url_patterns if patterns is None else patterns:
        if isinstance(entry, URLResolver):
            names = (*namespaces, entry.namespace) if entry.namespace else namespaces
            yield from walk(entry.url_patterns, names, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            name = ":".join((*namespaces, entry.name)) if entry.name else _func_path(entry.callback)
            yield prefix + str(entry.pattern), name, entry.callback


class RouteCoverageTests(SimpleTestCase):
    def setUp(self):
        self.routes = list(walk())
        self.known = set(settings.REQUEST_RATE_LIMITS["scopes"])

    def test_the_walk_sees_the_whole_site(self):
        self.assertGreater(len(self.routes), 600)
        self.assertTrue(any(route.startswith("admin/") for route, _name, _view in self.routes))
        self.assertTrue(any(route.startswith("admin-api/") for route, _name, _view in self.routes))

    def test_every_route_has_a_scope_or_a_reasoned_exemption(self):
        problems = []
        sources = set()
        for route, name, view in self.routes:
            for method in ("GET", "POST", "DELETE"):
                found = classify_route(view, name, method)
                if found is None:
                    scope = fallback("/" + route, method, signed_in=False)
                    sources.add("fallback")
                elif found.exempt is not None:
                    scope = None
                    sources.add("exempt")
                    if not found.exempt.strip():
                        problems.append(f"{route} {method}: exemption without a reason")
                else:
                    scope = found.scope
                    sources.add(found.source)
                if scope is not None and scope not in self.known:
                    problems.append(f"{route} {method}: unknown scope {scope!r}")
        self.assertEqual(problems, [])
        self.assertLessEqual({"fallback", "exempt", "route"}, sources)

    def test_the_fallback_scopes_exist_for_reads_and_writes(self):
        for signed_in in (False, True):
            for method in ("GET", "POST"):
                for path in ("/news/", "/admin/x/", "/admin-api/x/"):
                    self.assertIn(fallback(path, method, signed_in), self.known)

    def test_every_table_entry_matches_a_route(self):
        names = {name for _route, name, _view in self.routes}
        paths = {view_path(view) for _route, _name, view in self.routes}
        tables = {**settings.REQUEST_RATE_LIMITS["routes"], **settings.REQUEST_RATE_LIMITS["exempt"]}
        registered, exemptions = scope_module.registered()
        stale = sorted(
            key for key in {*tables, *registered, *exemptions} if key not in names | paths and key not in DEBUG_ONLY
        )
        self.assertEqual(stale, [])

    def test_user_initiated_sign_in_and_verification_routes_are_p0(self):
        by_name = {name: view for _route, name, view in self.routes}
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        for name in P0_ROUTES:
            with self.subTest(route=name):
                found = classify_route(by_name[name], name, "POST")
                self.assertIsNotNone(found)
                self.assertEqual(scopes[found.scope]["tier"], "p0")

    def test_heavy_and_ai_routes_are_p3(self):
        by_name = {name: view for _route, name, view in self.routes}
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        for name in (
            "projects:projects-all",
            "projects:projects-past-all",
            "system_intelligence:public-assistant-chat",
        ):
            with self.subTest(route=name):
                self.assertEqual(scopes[classify_route(by_name[name], name, "GET").scope]["tier"], "p3")

    def test_the_legal_opt_out_and_the_stylesheet_are_exempt(self):
        by_name = {name: view for _route, name, view in self.routes}
        for name in ("mail:oneclick-unsubscribe", "layout-theme", "robots-txt"):
            with self.subTest(route=name):
                self.assertTrue(classify_route(by_name[name], name, "POST").exempt)
