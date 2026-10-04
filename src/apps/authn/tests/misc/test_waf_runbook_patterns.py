"""The regex patterns in the WAF runbook (``docs/deployment/waf-rate-limits.md``) against the real URL configuration.

AWS WAF refuses a regex pattern longer than 200 characters and a pattern set with more than 10 patterns, and a pattern
that drifts from the routes either leaves an endpoint unprotected or rate-limits one every signed-in tab calls
(``/authn/refresh/``). This reads the patterns out of the runbook and checks them against every route Django serves.
"""

import re
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import Resolver404, URLResolver, get_resolver, resolve
from django.urls.resolvers import RoutePattern

RUNBOOK = Path(settings.BASE_DIR).parent / "docs" / "deployment" / "waf-rate-limits.md"

# AWS WAF fixed quotas (https://docs.aws.amazon.com/waf/latest/developerguide/limits.html).
MAX_PATTERN_LENGTH = 200
MAX_PATTERNS_PER_SET = 10

# The three endpoint lists of the runbook, section 3 (paths as the origin serves them).
CREDENTIAL_PATHS = {
    "/authn/login/",
    "/authn/login/verify-code/",
    "/authn/email-auth/verify-code/",
    "/authn/register/verify-code/",
    "/authn/phone-auth/verify-code/",
    "/authn/password-reset/verify-code/",
    "/authn/password-reset/confirm/",
    "/mail/login-link/",
    "/mail/magic-login/",
    "/authn/impersonate-login/",
    "/admin/login/",
}
SEND_PATHS = {
    "/authn/send-verification/challenge/",
    "/admin/send-verification/challenge/",
    "/authn/email-auth/request-code/",
    "/authn/login/request-code/",
    "/authn/register/",
    "/authn/register/resend-code/",
    "/authn/password-reset/request-code/",
    "/authn/phone-auth/request-code/",
}
# The two anonymous endpoints whose in-app limits are keyed on a value the caller mints (visitor id, visitor token).
ANONYMOUS_WRITE_PATHS = {
    "/analytics/pageview/",
    "/assistant/chat/",
}
PATH_SETS = {"A": CREDENTIAL_PATHS, "B": SEND_PATHS, "C": ANONYMOUS_WRITE_PATHS}
LISTED_PATHS = CREDENTIAL_PATHS | SEND_PATHS | ANONYMOUS_WRITE_PATHS

# Paths that must never be rate-limited by these rules, whether or not they are routes.
NEVER_MATCHED = (
    "/authn/refresh/",
    "/authn/session/",
    "/authn/logout/",
    "/authn/public-key/",
    "/authn/profile/",
    "/authn/send-verification/requests/3f2b8c1e-4a5d-4e6f-8a9b-0c1d2e3f4a5b/",
    "/authn/change-password/request-code/",
    "/authn/login/extra/",
    "/authn/loginx/",
    "/authn/register/verify-code/extra/",
    "/xauthn/login/",
    "/api/api/authn/login/",
    "/apiauthn/login/",
    "/authn/login/?next=/authn/refresh/",
    "/mail/unsubscribe/sample-token/",
    "/mail/ses/events/",
    "/admin/",
    "/admin/logout/",
    "/admin/login/extra/",
    "/health/",
    "/",
    # Around set C: the token hand-out every page load calls, and lookalikes of the two anonymous writes.
    "/assistant/config/",
    "/assistant/",
    "/assistant/chat/extra/",
    "/assistant/chatx/",
    "/assistant/chat/config/",
    "/xassistant/chat/",
    "/api/api/assistant/chat/",
    "/apiassistant/chat/",
    "/analytics/",
    "/analytics/pageview/extra/",
    "/analytics/pageviews/",
    "/analytics/pageview/assistant/chat/",
    "/xanalytics/pageview/",
    "/api/api/analytics/pageview/",
    "/analytics/pageview/?next=/assistant/chat/",
    "/projects/past-ai-search/",
)

CONVERTER_SAMPLES = {
    "uuid": "3f2b8c1e-4a5d-4e6f-8a9b-0c1d2e3f4a5b",
    "str": "sample-token",
    "slug": "sample-slug",
    "int": "7",
    "path": "nested/sample",
}


def runbook_patterns() -> dict[str, list[str]]:
    """``{"A": [...], "B": [...], "C": [...]}``: the patterns listed in the runbook as ``A1: ^...$`` lines."""
    sets: dict[str, list[str]] = {}
    for line in RUNBOOK.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Z])\d+: (\^\S+\$)", line.strip())
        if match:
            sets.setdefault(match.group(1), []).append(match.group(2))
    return sets


def served_paths(patterns=None, prefix="/"):
    """One concrete path for every ``path()`` route Django serves (converters filled with a sample value)."""
    for entry in get_resolver().url_patterns if patterns is None else patterns:
        if not isinstance(entry.pattern, RoutePattern):
            continue
        route = prefix + re.sub(
            r"<(?:(\w+):)?\w+>", lambda found: CONVERTER_SAMPLES[found.group(1) or "str"], str(entry.pattern)
        )
        if isinstance(entry, URLResolver):
            yield from served_paths(entry.url_patterns, route)
        else:
            yield route


def edge_variants(path: str):
    """``path`` as the edge can see it: with and without the Amplify ``/api`` prefix and the trailing slash."""
    bare = path.rstrip("/")
    for prefix in ("", "/api"):
        yield prefix + path
        if bare and bare != path:
            yield prefix + bare


@skipUnless(RUNBOOK.exists(), "The docs directory is not part of this checkout")
class WafRunbookPatternTests(SimpleTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.patterns = runbook_patterns()

    def matches(self, set_name: str, path: str) -> bool:
        # A WAF regex pattern set matches when any of its patterns matches.
        return any(re.search(pattern, path) for pattern in self.patterns[set_name])

    def matching_sets(self, path: str) -> list[str]:
        return [set_name for set_name in sorted(self.patterns) if self.matches(set_name, path)]

    def test_the_runbook_lists_the_three_pattern_sets(self):
        self.assertEqual(sorted(self.patterns), sorted(PATH_SETS))
        self.assertEqual([len(self.patterns[set_name]) for set_name in ("A", "B", "C")], [2, 2, 1])

    def test_the_documented_pattern_lengths_are_the_real_ones(self):
        """The runbook states each pattern's length next to the 200-character quota."""
        lengths = [len(pattern) for set_name in sorted(self.patterns) for pattern in self.patterns[set_name]]
        stated = re.search(r"\(((?:\d+, )+\d+ and \d+) characters\)", RUNBOOK.read_text(encoding="utf-8"))

        self.assertIsNotNone(stated)
        self.assertEqual([int(number) for number in re.findall(r"\d+", stated.group(1))], lengths)

    def test_every_pattern_fits_the_waf_quotas(self):
        for set_name, patterns in self.patterns.items():
            self.assertLessEqual(len(patterns), MAX_PATTERNS_PER_SET, set_name)
            for pattern in patterns:
                with self.subTest(pattern=pattern):
                    self.assertLessEqual(len(pattern), MAX_PATTERN_LENGTH)
                    re.compile(pattern)

    def test_the_documented_paths_are_real_routes(self):
        for path in sorted(LISTED_PATHS):
            with self.subTest(path=path):
                resolve(path)

    def test_the_lists_do_not_overlap(self):
        self.assertEqual(sum(len(paths) for paths in PATH_SETS.values()), len(LISTED_PATHS))

    def test_the_listed_paths_match_their_own_set_only_in_every_edge_form(self):
        for set_name, paths in PATH_SETS.items():
            for path in sorted(paths):
                for variant in edge_variants(path):
                    with self.subTest(set=set_name, path=variant):
                        self.assertEqual(self.matching_sets(variant), [set_name])

    def test_set_c_covers_exactly_the_two_anonymous_write_endpoints(self):
        self.assertEqual(
            sorted(variant for path in ANONYMOUS_WRITE_PATHS for variant in edge_variants(path)),
            [
                "/analytics/pageview",
                "/analytics/pageview/",
                "/api/analytics/pageview",
                "/api/analytics/pageview/",
                "/api/assistant/chat",
                "/api/assistant/chat/",
                "/assistant/chat",
                "/assistant/chat/",
            ],
        )
        served = set(served_paths())
        self.assertEqual(
            {path for path in served if any(self.matches("C", variant) for variant in edge_variants(path))},
            ANONYMOUS_WRITE_PATHS,
        )

    def test_no_other_route_is_matched(self):
        """Every route Django serves that is not in a list stays outside all three sets, in every edge form."""
        served = set(served_paths())
        self.assertTrue(LISTED_PATHS <= served)  # the walk really covers the listed routes
        self.assertGreater(len(served), 100)
        for path in sorted(served - LISTED_PATHS):
            for variant in edge_variants(path):
                with self.subTest(path=variant):
                    self.assertEqual(self.matching_sets(variant), [])

    def test_excluded_and_lookalike_paths_are_never_matched(self):
        for path in NEVER_MATCHED:
            for variant in edge_variants(path):
                with self.subTest(path=variant):
                    self.assertEqual(self.matching_sets(variant), [])

    def test_the_excluded_routes_exist(self):
        """The exclusions the runbook explains are real routes (so the negative checks above mean something)."""
        for path in (
            "/authn/refresh/",
            "/authn/session/",
            "/authn/logout/",
            "/authn/public-key/",
            "/assistant/config/",
            "/projects/past-ai-search/",
        ):
            with self.subTest(path=path):
                try:
                    resolve(path)
                except Resolver404:
                    self.fail(f"{path} is not a route any more: update the runbook and this test")
