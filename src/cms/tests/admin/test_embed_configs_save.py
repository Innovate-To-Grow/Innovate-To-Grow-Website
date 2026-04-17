"""Unit tests for save_embed_configs_from_json admin save logic.

Covers the slug validation / deduplication / global-uniqueness / block-reference
rules implemented in cms.admin.cms.page_admin.editor.save_embed_configs_from_json.

Each test invokes the function directly with a synthetic POST request and a
fake messages sink so assertions can inspect both persisted state and the
warning/error messages emitted to the admin.
"""

from django.test import RequestFactory, TestCase

from cms.admin.cms.page_admin.editor import save_embed_configs_from_json
from cms.models import CMSBlock, CMSPage


class FakeMessages:
    """Collector that mimics django.contrib.messages' warning/error API."""

    def __init__(self):
        self.warnings: list[str] = []
        self.errors: list[str] = []

    # noinspection PyUnusedLocal
    def warning(self, request, text):
        self.warnings.append(text)

    # noinspection PyUnusedLocal
    def error(self, request, text):
        self.errors.append(text)


class SaveEmbedConfigsTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.factory = RequestFactory()
        self.page = CMSPage.objects.create(
            slug="embed-host",
            route="/embed-host",
            title="Embed Host",
            status="draft",
        )
        # Three blocks, sort_order 0..2
        for i in range(3):
            CMSBlock.objects.create(
                page=self.page,
                block_type="rich_text",
                sort_order=i,
                data={"body_html": f"<p>Block {i}</p>"},
            )

    def _call(self, payload, messages=None):
        """Invoke the save function with a POST request carrying embed_configs_json."""
        import json

        request = self.factory.post("/fake", data={"embed_configs_json": json.dumps(payload)})
        msgs = messages or FakeMessages()
        save_embed_configs_from_json(request, self.page, msgs)
        self.page.refresh_from_db()
        return msgs

    def _call_raw(self, body, messages=None):
        """Invoke with a raw (possibly non-JSON) body."""
        request = self.factory.post("/fake", data={"embed_configs_json": body})
        msgs = messages or FakeMessages()
        save_embed_configs_from_json(request, self.page, msgs)
        self.page.refresh_from_db()
        return msgs

    # --- Happy path ---

    def test_saves_valid_single_entry(self):
        msgs = self._call(
            [
                {"slug": "widget-a", "admin_label": "Widget A", "block_sort_orders": [0, 1]},
            ]
        )
        self.assertEqual(msgs.warnings, [])
        self.assertEqual(len(self.page.embed_configs), 1)
        self.assertEqual(self.page.embed_configs[0]["slug"], "widget-a")
        self.assertEqual(self.page.embed_configs[0]["admin_label"], "Widget A")
        self.assertEqual(self.page.embed_configs[0]["block_sort_orders"], [0, 1])

    def test_saves_multiple_entries(self):
        self._call(
            [
                {"slug": "widget-a", "admin_label": "", "block_sort_orders": [0]},
                {"slug": "widget-b", "admin_label": "", "block_sort_orders": [1, 2]},
            ]
        )
        self.assertEqual(len(self.page.embed_configs), 2)
        self.assertEqual(self.page.embed_configs[0]["slug"], "widget-a")
        self.assertEqual(self.page.embed_configs[1]["slug"], "widget-b")

    def test_block_sort_orders_are_sorted(self):
        """block_sort_orders are stored in ascending order for stable ordering."""
        self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": [2, 0, 1]},
            ]
        )
        self.assertEqual(self.page.embed_configs[0]["block_sort_orders"], [0, 1, 2])

    def test_slug_is_normalized_to_lowercase_and_trimmed(self):
        self._call(
            [
                {"slug": "  MIXED-Case  ", "admin_label": "", "block_sort_orders": [0]},
            ]
        )
        self.assertEqual(self.page.embed_configs[0]["slug"], "mixed-case")

    def test_admin_label_is_trimmed(self):
        self._call(
            [
                {"slug": "w", "admin_label": "   padded   ", "block_sort_orders": [0]},
            ]
        )
        self.assertEqual(self.page.embed_configs[0]["admin_label"], "padded")

    def test_duplicate_block_refs_are_deduplicated(self):
        self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": [0, 0, 1, 1, 0]},
            ]
        )
        self.assertEqual(self.page.embed_configs[0]["block_sort_orders"], [0, 1])

    # --- Request-level errors ---

    def test_missing_field_is_noop(self):
        """If embed_configs_json is empty string, do not clear existing configs."""
        self.page.embed_configs = [
            {"slug": "existing", "admin_label": "", "block_sort_orders": [0]},
        ]
        self.page.save(update_fields=["embed_configs"])

        request = self.factory.post("/fake", data={})
        msgs = FakeMessages()
        save_embed_configs_from_json(request, self.page, msgs)
        self.page.refresh_from_db()

        self.assertEqual(msgs.errors, [])
        self.assertEqual(len(self.page.embed_configs), 1)
        self.assertEqual(self.page.embed_configs[0]["slug"], "existing")

    def test_invalid_json_emits_error(self):
        msgs = self._call_raw("not-json{{{")
        self.assertTrue(any("Invalid embed configs JSON" in e for e in msgs.errors))

    def test_non_array_json_emits_error(self):
        msgs = self._call_raw('{"slug": "x"}')
        self.assertTrue(any("expected a JSON array" in e for e in msgs.errors))

    # --- Entry-level validation ---

    def test_non_dict_entry_is_dropped(self):
        msgs = self._call(
            [
                "not-a-dict",
                {"slug": "valid", "admin_label": "", "block_sort_orders": [0]},
            ]
        )
        self.assertTrue(any("not a JSON object" in w for w in msgs.warnings))
        self.assertEqual(len(self.page.embed_configs), 1)
        self.assertEqual(self.page.embed_configs[0]["slug"], "valid")

    def test_missing_slug_is_dropped(self):
        msgs = self._call(
            [
                {"slug": "", "admin_label": "", "block_sort_orders": [0]},
            ]
        )
        self.assertTrue(any("slug is required" in w for w in msgs.warnings))
        self.assertEqual(self.page.embed_configs, [])

    def test_invalid_slug_format_is_dropped(self):
        """Slugs with whitespace, underscores, leading hyphens, etc. are dropped
        with a kebab-case warning. (Uppercase is NOT rejected — it's normalized
        to lowercase by the input pipeline; see test_slug_is_normalized_*.)
        """
        for bad in ["with space", "-leading-hyphen", "under_score", "bad!punct"]:
            msgs = self._call(
                [
                    {"slug": bad, "admin_label": "", "block_sort_orders": [0]},
                ]
            )
            self.assertEqual(
                self.page.embed_configs,
                [],
                f"Invalid slug '{bad}' should have been dropped, got {self.page.embed_configs}",
            )
            self.assertTrue(
                any("kebab-case" in w for w in msgs.warnings),
                f"Expected kebab-case warning for '{bad}', got {msgs.warnings}",
            )

    def test_uppercase_slug_is_normalized_not_rejected(self):
        """ASCII uppercase slugs are lowercased by the input pipeline, not rejected."""
        self._call(
            [
                {"slug": "ALL-CAPS", "admin_label": "", "block_sort_orders": [0]},
            ]
        )
        self.assertEqual(len(self.page.embed_configs), 1)
        self.assertEqual(self.page.embed_configs[0]["slug"], "all-caps")

    def test_block_sort_orders_not_a_list_is_dropped(self):
        msgs = self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": "not-a-list"},
            ]
        )
        self.assertTrue(any("must be a list" in w for w in msgs.warnings))
        self.assertEqual(self.page.embed_configs, [])

    def test_non_integer_block_refs_are_skipped(self):
        msgs = self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": [0, "oops", None, 1]},
            ]
        )
        # The entry itself is kept; invalid refs silently dropped.
        self.assertEqual(self.page.embed_configs[0]["block_sort_orders"], [0, 1])
        # No warning expected for individual invalid refs (graceful degradation).
        self.assertFalse(any("oops" in w for w in msgs.warnings))

    def test_refs_to_nonexistent_blocks_are_skipped(self):
        msgs = self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": [0, 99, 2]},
            ]
        )
        self.assertEqual(self.page.embed_configs[0]["block_sort_orders"], [0, 2])
        self.assertEqual(msgs.warnings, [])  # silent skip

    def test_entry_with_no_valid_blocks_is_dropped(self):
        msgs = self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": [99, 100]},
            ]
        )
        self.assertTrue(any("no valid block references" in w for w in msgs.warnings))
        self.assertEqual(self.page.embed_configs, [])

    # --- Slug uniqueness ---

    def test_duplicate_slug_on_same_page_is_dropped(self):
        msgs = self._call(
            [
                {"slug": "dup", "admin_label": "First", "block_sort_orders": [0]},
                {"slug": "dup", "admin_label": "Second", "block_sort_orders": [1]},
            ]
        )
        self.assertTrue(any("duplicates another embed on this page" in w for w in msgs.warnings))
        self.assertEqual(len(self.page.embed_configs), 1)
        self.assertEqual(self.page.embed_configs[0]["admin_label"], "First")

    def test_slug_used_on_another_page_is_dropped(self):
        """Global uniqueness: if another page already uses this slug, reject."""
        other = CMSPage.objects.create(
            slug="other",
            route="/other",
            title="Other",
            status="draft",
            embed_configs=[{"slug": "taken", "admin_label": "", "block_sort_orders": [0]}],
        )
        CMSBlock.objects.create(page=other, block_type="rich_text", sort_order=0, data={})

        msgs = self._call(
            [
                {"slug": "taken", "admin_label": "", "block_sort_orders": [0]},
            ]
        )
        self.assertTrue(any("already used by another page" in w for w in msgs.warnings))
        self.assertEqual(self.page.embed_configs, [])

    def test_reusing_same_slug_on_same_page_across_saves_ok(self):
        """A page saving its OWN existing slug must not collide with itself."""
        self.page.embed_configs = [
            {"slug": "self-use", "admin_label": "", "block_sort_orders": [0]},
        ]
        self.page.save(update_fields=["embed_configs"])

        msgs = self._call(
            [
                {"slug": "self-use", "admin_label": "Kept", "block_sort_orders": [0, 1]},
            ]
        )
        self.assertEqual(msgs.warnings, [])
        self.assertEqual(len(self.page.embed_configs), 1)
        self.assertEqual(self.page.embed_configs[0]["admin_label"], "Kept")
        self.assertEqual(self.page.embed_configs[0]["block_sort_orders"], [0, 1])

    # --- Empty / clearing ---

    def test_empty_array_clears_all_configs(self):
        self.page.embed_configs = [
            {"slug": "to-remove", "admin_label": "", "block_sort_orders": [0]},
        ]
        self.page.save(update_fields=["embed_configs"])

        msgs = self._call([])
        self.assertEqual(msgs.warnings, [])
        self.assertEqual(self.page.embed_configs, [])

    def test_save_updates_updated_at(self):
        """The save writes both embed_configs and updated_at."""
        original = self.page.updated_at
        self._call(
            [
                {"slug": "w", "admin_label": "", "block_sort_orders": [0]},
            ]
        )
        self.assertGreaterEqual(self.page.updated_at, original)
