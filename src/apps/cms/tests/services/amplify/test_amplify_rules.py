"""Amplify redirect rules: merging app-owned rules with the console's, and the single-writer workflow."""

from django.test import SimpleTestCase

from apps.cms.services.amplify import (
    amplify_source_variants,
    merge_amplify_rules,
)

from .amplify_helpers import _base_rules


class AmplifyRuleMergeTests(SimpleTestCase):
    def test_source_variants_preserve_case_and_add_trailing_slash(self):
        self.assertEqual(amplify_source_variants("/FAQs"), ("/FAQs", "/FAQs/"))
        self.assertEqual(amplify_source_variants("/"), ("/",))

    def test_merge_replaces_owned_rules_and_preserves_unmanaged_order(self):
        fallback = {
            "source": "</^[^.]+$/>",
            "target": "/index.html",
            "status": "200",
        }
        existing = [
            {"source": "/api/<*>", "target": "https://api.example/<*>", "status": "200"},
            {"source": "/Old", "target": "/stale", "status": "301"},
            {"source": "/Old/", "target": "/stale", "status": "301"},
            {"source": "/inactive", "target": "/stale", "status": "301"},
            fallback,
            {"source": "/asset", "target": "/asset.html", "status": "200"},
        ]

        desired, active_count, managed_count = merge_amplify_rules(
            existing_rules=existing,
            all_redirects=[
                {"source_path": "/Old", "destination_path": "/new", "is_active": True},
                {
                    "source_path": "/inactive",
                    "destination_path": "/new",
                    "is_active": False,
                    "edge_rule_managed": True,
                },
            ],
        )

        self.assertEqual(active_count, 1)
        self.assertEqual(managed_count, 2)
        self.assertEqual(
            desired,
            [
                existing[0],
                {"source": "/Old", "target": "/new", "status": "301"},
                {"source": "/Old/", "target": "/new", "status": "301"},
                fallback,
                existing[-1],
            ],
        )

    def test_never_active_inactive_redirect_does_not_claim_manual_rule(self):
        manual_rule = {"source": "/inactive", "target": "/manual", "status": "302"}

        desired, active_count, managed_count = merge_amplify_rules(
            existing_rules=[manual_rule],
            all_redirects=[
                {
                    "source_path": "/inactive",
                    "destination_path": "/new",
                    "is_active": False,
                    "edge_rule_managed": False,
                    "edge_sync_attempted_at": "historical-attempt",
                    "edge_synced_at": "historical-success",
                },
            ],
        )

        self.assertEqual(desired, [manual_rule])
        self.assertEqual(active_count, 0)
        self.assertEqual(managed_count, 0)

    def test_canonical_base_rules_replace_stale_owned_rules_and_keep_spa_last(self):
        manual_rule = {"source": "/robots.txt", "target": "/robots-prod.txt", "status": "200"}
        stale_fallback = {"source": "/<*>", "target": "/index.html", "status": "404-200"}

        desired, active_count, managed_count = merge_amplify_rules(
            existing_rules=[
                {"source": "/sitemap.xml", "target": "https://old.example/sitemap.xml", "status": "200"},
                {"source": "/api/<*>", "target": "https://old.example/<*>", "status": "200"},
                {"source": "/admin/<*>", "target": "https://old.example/admin/<*>", "status": "200"},
                manual_rule,
                stale_fallback,
            ],
            all_redirects=[
                {
                    "source_path": "/Legacy",
                    "destination_path": "/target",
                    "is_active": True,
                    "edge_rule_managed": False,
                }
            ],
            base_rules=_base_rules(),
        )

        self.assertEqual(active_count, 1)
        self.assertEqual(managed_count, 2)
        self.assertEqual(
            desired,
            [
                *_base_rules()[:-1],
                {"source": "/Legacy", "target": "/target", "status": "301"},
                {"source": "/Legacy/", "target": "/target", "status": "301"},
                manual_rule,
                _base_rules()[-1],
            ],
        )

    def test_literal_index_rewrite_is_preserved_as_an_unrelated_rule(self):
        literal_rewrite = {
            "source": "/standalone-shell",
            "target": "/index.html",
            "status": "200",
        }

        desired, _active_count, _managed_count = merge_amplify_rules(
            existing_rules=[literal_rewrite],
            all_redirects=[],
            base_rules=_base_rules(),
        )

        self.assertEqual(desired, [*_base_rules()[:-1], literal_rewrite, _base_rules()[-1]])

    def test_partial_regex_index_rewrite_is_preserved_as_an_unrelated_rule(self):
        partial_regex_rewrite = {
            "source": r"</^/campaign/.+$/>",
            "target": "/index.html",
            "status": "200",
        }

        desired, _active_count, _managed_count = merge_amplify_rules(
            existing_rules=[partial_regex_rewrite],
            all_redirects=[],
            base_rules=_base_rules(),
        )

        self.assertEqual(desired, [*_base_rules()[:-1], partial_regex_rewrite, _base_rules()[-1]])

    def test_exact_redirects_precede_preserved_wildcard_rules(self):
        broad_rule = {"source": "/legacy/<*>", "target": "/legacy-shell", "status": "200"}

        desired, _active_count, _managed_count = merge_amplify_rules(
            existing_rules=[broad_rule],
            all_redirects=[
                {
                    "source_path": "/legacy/specific",
                    "destination_path": "/target",
                    "is_active": True,
                    "edge_rule_managed": False,
                }
            ],
            base_rules=_base_rules(),
        )

        self.assertEqual(
            desired,
            [
                *_base_rules()[:-1],
                {"source": "/legacy/specific", "target": "/target", "status": "301"},
                {"source": "/legacy/specific/", "target": "/target", "status": "301"},
                broad_rule,
                _base_rules()[-1],
            ],
        )
