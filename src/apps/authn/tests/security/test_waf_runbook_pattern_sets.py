from unittest import skipUnless

from django.urls import Resolver404, resolve

from apps.authn.tests.security.test_waf_runbook_patterns import (
    ANONYMOUS_WRITE_PATHS,
    LISTED_PATHS,
    NEVER_MATCHED,
    PATH_SETS,
    RUNBOOK,
    _WafRunbookPatternCase,
    edge_variants,
    served_paths,
)


@skipUnless(RUNBOOK.exists(), "The docs directory is not part of this checkout")
class WafRunbookPatternTests(_WafRunbookPatternCase):
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
