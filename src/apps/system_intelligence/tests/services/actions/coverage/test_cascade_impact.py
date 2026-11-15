from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import models
from django.test import TestCase

from apps.cms.models import NewsFeedSource
from apps.system_intelligence.services.actions.db.cascade import (
    cascade_summary,
    collect_cascade_impact,
)
from apps.system_intelligence.services.actions.exceptions import ActionRequestError
from apps.system_intelligence.services.actions.orm import safety as orm_safety


# ---------------------------------------------------------------------------
# db/cascade.py
# ---------------------------------------------------------------------------
class CascadeImpactTests(TestCase):
    def _make_event_with_tickets(self, ticket_count=2):
        import datetime

        from apps.event.models import Event, Ticket

        event = Event.objects.create(
            name="Demo Day",
            date=datetime.date(2025, 6, 15),
            end_date=datetime.date(2025, 6, 15),
            location="V",
            description="d",
        )
        for index in range(ticket_count):
            Ticket.objects.create(event=event, name=f"Ticket {index}")
        return event

    def test_collect_counts_related_rows_and_excludes_target(self):
        event = self._make_event_with_tickets(2)
        impact = collect_cascade_impact(event)
        # The two tickets are counted; the event row itself is excluded.
        self.assertEqual(impact["total"], 2)
        ticket_entry = next(item for item in impact["related"] if item["model"] == "event.Ticket")
        self.assertEqual(ticket_entry["count"], 2)
        self.assertNotIn("event.Event", [item["model"] for item in impact["related"]])

    def test_collect_counts_sibling_rows_of_target_class(self):
        # Drive the "related_model is obj.__class__" branch with extra rows of the
        # target's own class so the self-discard count is non-zero.
        target = NewsFeedSource.objects.create(name="Target", source_key="target", feed_url="https://example.com/t.xml")
        sibling = NewsFeedSource.objects.create(
            name="Sibling", source_key="sibling", feed_url="https://example.com/s.xml"
        )

        def fake_collect(self_collector, objs):
            self_collector.data = {NewsFeedSource: {target, sibling}}

        with patch(
            "apps.system_intelligence.services.actions.db.cascade.Collector.collect",
            autospec=True,
            side_effect=fake_collect,
        ):
            impact = collect_cascade_impact(target)
        self.assertEqual(impact["total"], 1)
        entry = next(item for item in impact["related"] if item["model"] == "cms.NewsFeedSource")
        self.assertEqual(entry["count"], 1)

    def test_collect_handles_collector_failure(self):
        source = NewsFeedSource.objects.create(name="Boom", source_key="boom", feed_url="https://example.com/b.xml")
        with patch(
            "apps.system_intelligence.services.actions.db.cascade.Collector.collect",
            side_effect=RuntimeError("boom"),
        ):
            impact = collect_cascade_impact(source)
        self.assertEqual(impact["total"], 0)
        self.assertEqual(impact["error"], "Could not enumerate cascade impact.")

    def test_cascade_summary_with_no_total_returns_base(self):
        self.assertEqual(cascade_summary("Base note", {"total": 0}), "Base note")

    def test_cascade_summary_with_base_appends_note(self):
        cascade = {
            "total": 5,
            "related": [
                {"model": "cms.NewsSyncLog", "count": 2},
                {"model": "cms.NewsArticle", "count": 2},
                {"model": "cms.A", "count": 1},
                {"model": "cms.B", "count": 1},
            ],
        }
        summary = cascade_summary("Delete it", cascade)
        self.assertTrue(summary.startswith("Delete it."))
        self.assertIn("Cascade will also remove 5 related record(s)", summary)
        # More than three related models -> trailing ellipsis.
        self.assertTrue(summary.endswith(", ...."))

    def test_cascade_summary_without_base_returns_note_only(self):
        cascade = {"total": 1, "related": [{"model": "cms.NewsSyncLog", "count": 1}]}
        summary = cascade_summary(None, cascade)
        self.assertTrue(summary.startswith("Cascade will also remove 1 related record(s)"))


# ---------------------------------------------------------------------------
# orm/safety.py
# ---------------------------------------------------------------------------
class OrmSafetyTests(TestCase):
    def test_resolve_unknown_model_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            orm_safety.resolve_model("cms", "DefinitelyNotAModel", write=False)
        self.assertIn("Unknown model 'cms.DefinitelyNotAModel'", str(cm.exception))

    def test_file_and_binary_fields_are_denied(self):
        file_field = models.FileField(name="attachment")
        self.assertTrue(orm_safety.is_field_denied(file_field, write=False))
        binary_field = models.BinaryField(name="blob")
        self.assertTrue(orm_safety.is_field_denied(binary_field, write=False))

    def test_auto_now_field_is_denied_for_write(self):
        # Force an otherwise-editable field to carry auto_now_add so the
        # auto-timestamp guard (not the editable guard) is the one that fires.
        auto_field = models.CharField(name="touched")
        auto_field.editable = True
        auto_field.primary_key = False
        auto_field.auto_now_add = True
        self.assertTrue(orm_safety.is_field_denied(auto_field, write=True))
        # Reads ignore the write-only auto-timestamp rule.
        self.assertFalse(orm_safety.is_field_denied(auto_field, write=False))

    def test_field_schema_reports_metadata(self):
        field = NewsFeedSource._meta.get_field("name")
        schema = orm_safety.field_schema(field)
        self.assertEqual(schema["name"], "name")
        self.assertEqual(schema["type"], "CharField")
        self.assertIn("required", schema)
        self.assertEqual(schema["choices"], [])

    def test_validate_selected_fields_rejects_non_list(self):
        with self.assertRaises(ActionRequestError) as cm:
            orm_safety.validate_selected_fields("name", {"name"})
        self.assertIn("fields must be a list", str(cm.exception))

    def test_validate_query_key_rejects_non_string(self):
        with self.assertRaises(ActionRequestError) as cm:
            orm_safety.validate_query_key(123, {"name"})
        self.assertIn("Query fields must be strings", str(cm.exception))

    def test_validate_query_key_rejects_disallowed_lookup(self):
        with self.assertRaises(ActionRequestError) as cm:
            orm_safety.validate_query_key("name__regex", {"name"})
        self.assertIn("Lookup 'regex' is not allowed", str(cm.exception))

    def test_coerce_jsonfield_returns_value_unchanged(self):
        json_field = models.JSONField(name="payload")
        sentinel = {"key": "value"}
        self.assertIs(orm_safety.coerce_field_value(json_field, sentinel), sentinel)

    def test_coerce_foreign_key_uses_target_field(self):
        # Permission.content_type targets ContentType's integer PK, so a string
        # value is coerced through the target field's to_python.
        fk_field = Permission._meta.get_field("content_type")
        coerced = orm_safety.coerce_field_value(fk_field, "123")
        self.assertEqual(coerced, 123)
