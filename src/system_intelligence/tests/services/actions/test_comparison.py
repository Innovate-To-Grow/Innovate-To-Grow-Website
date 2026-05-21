from cms.models import CMSPage, NewsFeedSource
from cms.models.content.news.sync_log import NewsSyncLog
from system_intelligence.models import SystemIntelligenceActionRequest
from system_intelligence.services import actions
from system_intelligence.services.actions.comparison import build_db_comparison

from .base import SystemIntelligenceActionBase


class SystemIntelligenceComparisonTests(SystemIntelligenceActionBase):
    def test_cms_comparison_falls_back_from_snapshots_and_truncates_large_text(self):
        long_text = "A" * 1200
        before = {
            "title": "Page",
            "route": "/page",
            "blocks": [
                {
                    "block_type": "rich_text",
                    "sort_order": 0,
                    "admin_label": "Main copy",
                    "data": {"body_html": "<p>Short</p>"},
                }
            ],
        }
        after = {
            "title": "Page",
            "route": "/page",
            "blocks": [
                {
                    "block_type": "rich_text",
                    "sort_order": 0,
                    "admin_label": "Main copy",
                    "data": {"body_html": f"<p>{long_text}</p>"},
                }
            ],
        }
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            title="Legacy CMS action",
            payload={"page": after},
            before_snapshot=before,
            after_snapshot=after,
            diff=[],
        )
        block = actions.serialize_action_request(action)["comparison"]["blocks"][0]
        self.assertEqual(block["before_text"], "Short")
        self.assertLessEqual(len(block["after_text"]), actions.COMPARISON_TEXT_LIMIT)
        self.assertTrue(block["after_text"].endswith("..."))


class BuildDbComparisonTests(SystemIntelligenceActionBase):
    def _row(self, comparison, field):
        for row in comparison["fields"] + comparison["context_fields"]:
            if row["field"] == field:
                return row
        raise AssertionError(f"field {field!r} not found in comparison rows")

    def test_boolean_renders_as_yes_no(self):
        before = {"name": "UC Merced", "is_active": True, "__repr__": "UC Merced"}
        after = {"name": "UC Merced", "is_active": False, "__repr__": "UC Merced"}
        comparison = build_db_comparison(NewsFeedSource, before, after, mode="update")
        is_active = self._row(comparison, "is_active")
        self.assertTrue(is_active["changed"])
        self.assertEqual(is_active["before_display"], "Yes")
        self.assertEqual(is_active["after_display"], "No")
        self.assertEqual(is_active["label"], "Is Active")
        self.assertEqual(is_active["type"], "BooleanField")

    def test_choice_uses_human_label(self):
        before = {"status": "draft", "title": "Page", "__repr__": "Page"}
        after = {"status": "published", "title": "Page", "__repr__": "Page"}
        comparison = build_db_comparison(CMSPage, before, after, mode="update")
        status = self._row(comparison, "status")
        self.assertEqual(status["before_display"], "Draft")
        self.assertEqual(status["after_display"], "Published")

    def test_foreign_key_uses_related_repr(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        before = {"feed_source_id": source.pk, "articles_created": 0}
        after = {"feed_source_id": source.pk, "articles_created": 5}
        comparison = build_db_comparison(NewsSyncLog, before, after, mode="update")
        fk_row = self._row(comparison, "feed_source_id")
        self.assertEqual(fk_row["type"], "ForeignKey")
        self.assertEqual(fk_row["before_display"], "UC Merced")
        self.assertEqual(fk_row["after_display"], "UC Merced")

    def test_foreign_key_missing_target_falls_back_to_id(self):
        before = {"feed_source_id": 999999, "articles_created": 0}
        after = {"feed_source_id": 999999, "articles_created": 1}
        comparison = build_db_comparison(NewsSyncLog, before, after, mode="update")
        fk_row = self._row(comparison, "feed_source_id")
        self.assertEqual(fk_row["before_display"], "#999999")

    def test_create_mode_marks_all_fields_changed(self):
        after = {
            "name": "New Feed",
            "source_key": "new",
            "feed_url": "https://example.com/new.xml",
            "is_active": True,
            "__repr__": "New Feed",
        }
        comparison = build_db_comparison(NewsFeedSource, {}, after, mode="create")
        self.assertEqual(comparison["mode"], "create")
        self.assertEqual(comparison["context_fields"], [])
        for row in comparison["fields"]:
            self.assertTrue(row["changed"])
            self.assertEqual(row["before_display"], "—")

    def test_delete_mode_renders_before_only(self):
        before = {
            "name": "Old Feed",
            "source_key": "old",
            "feed_url": "https://example.com/old.xml",
            "is_active": False,
            "__repr__": "Old Feed",
        }
        comparison = build_db_comparison(NewsFeedSource, before, {}, mode="delete")
        self.assertEqual(comparison["mode"], "delete")
        for row in comparison["fields"]:
            self.assertTrue(row["changed"])
            self.assertEqual(row["after_display"], "—")

    def test_repr_key_is_skipped(self):
        before = {"name": "A", "__repr__": "A"}
        after = {"name": "B", "__repr__": "B"}
        comparison = build_db_comparison(NewsFeedSource, before, after, mode="update")
        self.assertEqual(comparison["record_repr"], "B")
        for row in comparison["fields"] + comparison["context_fields"]:
            self.assertNotEqual(row["field"], "__repr__")

    def test_unchanged_fields_land_in_context_fields(self):
        before = {"name": "UC Merced", "is_active": True, "source_key": "ucm", "__repr__": "UC Merced"}
        after = {"name": "UC Merced", "is_active": False, "source_key": "ucm", "__repr__": "UC Merced"}
        comparison = build_db_comparison(NewsFeedSource, before, after, mode="update")
        changed_field_names = [row["field"] for row in comparison["fields"]]
        context_field_names = [row["field"] for row in comparison["context_fields"]]
        self.assertEqual(changed_field_names, ["is_active"])
        self.assertIn("name", context_field_names)
        self.assertIn("source_key", context_field_names)
        for row in comparison["context_fields"]:
            self.assertFalse(row["changed"])

    def test_unknown_field_falls_back_to_humanized_label(self):
        before = {"some_unknown_field": "old"}
        after = {"some_unknown_field": "new"}
        comparison = build_db_comparison(NewsFeedSource, before, after, mode="update")
        row = self._row(comparison, "some_unknown_field")
        self.assertEqual(row["label"], "Some Unknown Field")
        self.assertEqual(row["type"], "Field")
        self.assertEqual(row["before_display"], "old")
        self.assertEqual(row["after_display"], "new")
