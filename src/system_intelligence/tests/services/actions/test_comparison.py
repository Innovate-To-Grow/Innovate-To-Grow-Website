from cms.models import CMSBlock, CMSPage, Menu
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
        before = {"name": "main", "is_active": True, "__repr__": "Main"}
        after = {"name": "main", "is_active": False, "__repr__": "Main"}
        comparison = build_db_comparison(Menu, before, after, mode="update")
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
        page = CMSPage.objects.create(title="Test Page", slug="test-fk", route="/test-fk", status="draft")
        before = {"page_id": page.pk, "sort_order": 0}
        after = {"page_id": page.pk, "sort_order": 1}
        comparison = build_db_comparison(CMSBlock, before, after, mode="update")
        fk_row = self._row(comparison, "page_id")
        self.assertEqual(fk_row["type"], "ForeignKey")
        self.assertEqual(fk_row["before_display"], str(page))
        self.assertEqual(fk_row["after_display"], str(page))

    def test_foreign_key_missing_target_falls_back_to_id(self):
        import uuid

        fake_pk = uuid.uuid4()
        before = {"page_id": fake_pk, "sort_order": 0}
        after = {"page_id": fake_pk, "sort_order": 1}
        comparison = build_db_comparison(CMSBlock, before, after, mode="update")
        fk_row = self._row(comparison, "page_id")
        self.assertEqual(fk_row["before_display"], f"#{fake_pk}")

    def test_create_mode_marks_all_fields_changed(self):
        after = {
            "name": "new-menu",
            "display_name": "New Menu",
            "is_active": True,
            "__repr__": "New Menu",
        }
        comparison = build_db_comparison(Menu, {}, after, mode="create")
        self.assertEqual(comparison["mode"], "create")
        self.assertEqual(comparison["context_fields"], [])
        for row in comparison["fields"]:
            self.assertTrue(row["changed"])
            self.assertEqual(row["before_display"], "—")

    def test_delete_mode_renders_before_only(self):
        before = {
            "name": "old-menu",
            "display_name": "Old Menu",
            "is_active": False,
            "__repr__": "Old Menu",
        }
        comparison = build_db_comparison(Menu, before, {}, mode="delete")
        self.assertEqual(comparison["mode"], "delete")
        for row in comparison["fields"]:
            self.assertTrue(row["changed"])
            self.assertEqual(row["after_display"], "—")

    def test_repr_key_is_skipped(self):
        before = {"name": "a", "__repr__": "A"}
        after = {"name": "b", "__repr__": "B"}
        comparison = build_db_comparison(Menu, before, after, mode="update")
        self.assertEqual(comparison["record_repr"], "B")
        for row in comparison["fields"] + comparison["context_fields"]:
            self.assertNotEqual(row["field"], "__repr__")

    def test_unchanged_fields_land_in_context_fields(self):
        before = {"name": "main", "is_active": True, "display_name": "Main", "__repr__": "Main"}
        after = {"name": "main", "is_active": False, "display_name": "Main", "__repr__": "Main"}
        comparison = build_db_comparison(Menu, before, after, mode="update")
        changed_field_names = [row["field"] for row in comparison["fields"]]
        context_field_names = [row["field"] for row in comparison["context_fields"]]
        self.assertEqual(changed_field_names, ["is_active"])
        self.assertIn("name", context_field_names)
        self.assertIn("display_name", context_field_names)
        for row in comparison["context_fields"]:
            self.assertFalse(row["changed"])

    def test_unknown_field_falls_back_to_humanized_label(self):
        before = {"some_unknown_field": "old"}
        after = {"some_unknown_field": "new"}
        comparison = build_db_comparison(Menu, before, after, mode="update")
        row = self._row(comparison, "some_unknown_field")
        self.assertEqual(row["label"], "Some Unknown Field")
        self.assertEqual(row["type"], "Field")
        self.assertEqual(row["before_display"], "old")
        self.assertEqual(row["after_display"], "new")
