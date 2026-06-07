"""Line-coverage tests for apps.system_intelligence.services.actions.

These exercise the helper, ORM-safety, comparison, cascade, context, and
approval code paths that the behavioural tests in this package do not reach.
"""

import datetime
import json
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import Member
from apps.cms.models import CMSPage, NewsFeedSource
from apps.cms.models.content.news.article import NewsArticle
from apps.cms.models.content.news.sync_log import NewsSyncLog
from apps.event.tests.helpers import make_admin
from apps.system_intelligence.models import SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions import approval, utils
from apps.system_intelligence.services.actions.cms import actions as cms_actions
from apps.system_intelligence.services.actions.cms import helpers as cms_helpers
from apps.system_intelligence.services.actions.cms.preview import normalize_cms_blocks
from apps.system_intelligence.services.actions.comparison import builders
from apps.system_intelligence.services.actions.comparison import field_display as fd
from apps.system_intelligence.services.actions.comparison.text import (
    extract_block_text,
    limit_comparison_text,
)
from apps.system_intelligence.services.actions.context import (
    current_conversation,
    current_user,
    current_user_id,
)
from apps.system_intelligence.services.actions.db.cascade import (
    cascade_summary,
    collect_cascade_impact,
)
from apps.system_intelligence.services.actions.exceptions import ActionRequestError
from apps.system_intelligence.services.actions.orm import records as orm_records
from apps.system_intelligence.services.actions.orm import safety as orm_safety

from .base import SystemIntelligenceActionBase


# ---------------------------------------------------------------------------
# records/__init__.py
# ---------------------------------------------------------------------------
class RecordsReadToolTests(TestCase):
    def test_list_database_models_includes_allowed_excludes_denied(self):
        # The full model list exceeds the truncation limit, so assert on the
        # rendered text rather than re-parsing the (truncated) JSON.
        result = actions.list_database_models()
        self.assertIn('"label": "cms.NewsFeedSource"', result)
        # A readable, writable model carries the writable flag.
        self.assertIn('"writable": true', result)
        # A denied model (CMSPage) must never be listed.
        self.assertNotIn('"label": "cms.CMSPage"', result)

    def test_list_database_models_sorted_by_label(self):
        # Patch get_models with a small, denial-free set so the JSON is not
        # truncated and ordering can be asserted exactly.
        models_in = [NewsSyncLog, NewsFeedSource]
        with patch(
            "apps.system_intelligence.services.actions.records.apps.get_models",
            return_value=models_in,
        ):
            result = actions.list_database_models()
        rows = json.loads(result)
        self.assertEqual([row["label"] for row in rows], ["cms.NewsFeedSource", "cms.NewsSyncLog"])

    def test_get_model_schema_lists_readable_and_writable_fields(self):
        result = actions.get_model_schema("cms", "NewsFeedSource")
        payload = json.loads(result)
        self.assertEqual(payload["model"], "cms.NewsFeedSource")
        self.assertEqual(payload["primary_key"], "id")
        readable = {f["name"] for f in payload["readable_fields"]}
        writable = {f["name"] for f in payload["writable_fields"]}
        self.assertIn("name", readable)
        self.assertIn("name", writable)
        # The UUID primary key is readable but not writable.
        self.assertIn("id", readable)
        self.assertNotIn("id", writable)

    def test_get_record_returns_safe_snapshot(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        result = actions.get_record("cms", "NewsFeedSource", str(source.pk))
        payload = json.loads(result)
        self.assertEqual(payload["name"], "UC Merced")
        self.assertEqual(payload["__repr__"], "UC Merced")

    def test_search_records_filters_orders_and_limits(self):
        NewsFeedSource.objects.create(name="Alpha", source_key="a", feed_url="https://example.com/a.xml")
        NewsFeedSource.objects.create(name="Beta", source_key="b", feed_url="https://example.com/b.xml")
        NewsFeedSource.objects.create(name="Gamma", source_key="g", feed_url="https://example.com/g.xml")
        result = actions.search_records(
            "cms",
            "NewsFeedSource",
            filters={"name__icontains": "a"},
            ordering="-name",
            fields=["name", "source_key"],
            limit=2,
        )
        payload = json.loads(result)
        self.assertEqual(payload["model"], "cms.NewsFeedSource")
        self.assertEqual(payload["shown"], 2)
        self.assertEqual(payload["total"], 3)
        # Ordering by -name then limited to 2 rows.
        self.assertEqual([row["name"] for row in payload["rows"]], ["Gamma", "Beta"])
        # Only the selected fields are present.
        self.assertEqual(set(payload["rows"][0]), {"name", "source_key"})

    def test_search_records_defaults_fields_when_none(self):
        NewsFeedSource.objects.create(name="Solo", source_key="solo", feed_url="https://example.com/s.xml")
        result = actions.search_records("cms", "NewsFeedSource")
        payload = json.loads(result)
        self.assertEqual(payload["shown"], 1)
        self.assertIn("name", payload["rows"][0])

    def test_search_records_rejects_non_dict_filters(self):
        with self.assertRaises(ActionRequestError) as cm:
            actions.search_records("cms", "NewsFeedSource", filters=["not", "a", "dict"])
        self.assertIn("filters must be an object", str(cm.exception))


# ---------------------------------------------------------------------------
# comparison/field_display.py
# ---------------------------------------------------------------------------
class FieldDisplayTests(TestCase):
    def test_boolean_non_bool_raw_renders_em_dash(self):
        # is_active is a BooleanField; a non True/False value falls through to EM_DASH.
        self.assertEqual(fd.display_value(NewsFeedSource, "is_active", "maybe"), fd.EM_DASH)

    def test_fk_none_and_empty_raw_render_em_dash(self):
        # Permission.content_type is an integer-PK FK; an empty raw renders the em dash.
        self.assertEqual(fd.display_value(Permission, "content_type", ""), fd.EM_DASH)

    def test_fk_resolves_related_repr(self):
        ct = ContentType.objects.get_for_model(NewsFeedSource)
        result = fd.display_value(Permission, "content_type", ct.pk)
        self.assertEqual(result, fd.record_repr(ct))

    def test_fk_bad_raw_falls_back_to_id(self):
        # A non-int string against an integer PK raises ValueError inside the
        # filter -> related is None -> "#<raw>".
        result = fd.display_value(Permission, "content_type", "abc")
        self.assertEqual(result, "#abc")

    def test_fk_missing_target_falls_back_to_id(self):
        result = fd.display_value(Permission, "content_type", 999999)
        self.assertEqual(result, "#999999")

    def test_datetime_object_formats_short(self):
        dt = timezone.make_aware(datetime.datetime(2025, 1, 2, 3, 4))
        result = fd.display_value(NewsArticle, "published_at", dt)
        self.assertNotEqual(result, fd.EM_DASH)
        self.assertNotIn("2025-01-02T", result)

    def test_datetime_unparseable_string_falls_back_to_truncate(self):
        result = fd.display_value(NewsArticle, "published_at", "not-a-datetime")
        self.assertEqual(result, "not-a-datetime")

    def test_datetime_non_string_non_datetime_falls_back(self):
        result = fd.display_value(NewsArticle, "published_at", 12345)
        self.assertEqual(result, "12345")

    def test_date_from_datetime_object(self):
        dt = datetime.datetime(2025, 5, 6, 7, 8)
        self.assertEqual(fd._format_date(dt), fd._format_date(datetime.date(2025, 5, 6)))

    def test_date_from_date_object(self):
        result = fd._format_date(datetime.date(2025, 5, 6))
        self.assertNotEqual(result, fd.EM_DASH)
        self.assertNotIn("not", result)

    def test_date_unparseable_string_falls_back(self):
        self.assertEqual(fd._format_date("garbage"), "garbage")

    def test_date_non_string_value_falls_back(self):
        self.assertEqual(fd._format_date(999), "999")

    def test_json_dict_with_many_keys_summarizes(self):
        raw = {f"k{i}": i for i in range(7)}
        self.assertEqual(fd._format_json(raw), "{7 keys}")

    def test_json_dict_small_renders_compact(self):
        self.assertEqual(fd._format_json({"a": 1}), '{"a": 1}')

    def test_json_value_non_container_falls_back(self):
        self.assertEqual(fd._format_json(42), "42")

    def test_stringify_unserializable_falls_back_to_str(self):
        class Weird:
            def __repr__(self):
                return "weird-object"

        with patch.object(fd.json, "dumps", side_effect=TypeError):
            self.assertEqual(fd._stringify(Weird()), "weird-object")

    def test_truncate_long_text_appends_ellipsis(self):
        result = fd._truncate("x" * 200)
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(len(result), fd.DEFAULT_TRUNCATE)


# ---------------------------------------------------------------------------
# cms/helpers.py
# ---------------------------------------------------------------------------
class CmsHelperLookupTests(TestCase):
    def setUp(self):
        self.page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")

    def test_find_by_slug(self):
        self.assertEqual(cms_helpers.find_cms_page(slug="about"), self.page)

    def test_find_by_route(self):
        self.assertEqual(cms_helpers.find_cms_page(route="/about"), self.page)

    def test_find_with_no_target_returns_none(self):
        self.assertIsNone(cms_helpers.find_cms_page())

    def test_serialize_none_page_returns_empty_dict(self):
        self.assertEqual(cms_helpers.serialize_cms_page(None), {})

    def test_build_proposal_rejects_non_dict_page_fields(self):
        with self.assertRaises(ActionRequestError) as cm:
            cms_helpers.build_cms_page_proposal(self.page, ["bad"], None)
        self.assertIn("page_fields must be an object", str(cm.exception))

    def test_build_proposal_rejects_unknown_field(self):
        with self.assertRaises(ActionRequestError) as cm:
            cms_helpers.build_cms_page_proposal(self.page, {"bogus_field": "x"}, None)
        self.assertIn("Unsupported CMS page field: bogus_field", str(cm.exception))

    def test_build_proposal_defaults_blocks_to_empty_for_new_page(self):
        proposed = cms_helpers.build_cms_page_proposal(None, {"slug": "new", "route": "/new", "title": "New"}, None)
        self.assertEqual(proposed["blocks"], [])

    def test_validate_payload_requires_core_fields(self):
        with self.assertRaises(ActionRequestError) as cm:
            cms_helpers.validate_cms_page_payload({"slug": "s", "route": "/r"}, None)
        self.assertIn("'title' is required", str(cm.exception))

    def test_validate_payload_rejects_unknown_status(self):
        payload = {"slug": "s", "route": "/r", "title": "T", "status": "bogus"}
        with self.assertRaises(ActionRequestError) as cm:
            cms_helpers.validate_cms_page_payload(payload, None)
        self.assertIn("Unsupported CMS page status: bogus", str(cm.exception))

    def test_validate_payload_surfaces_full_clean_errors(self):
        # A duplicate slug triggers a model validation error via full_clean().
        CMSPage.objects.create(slug="dupe", route="/dupe", title="Dupe", status="draft")
        payload = {"slug": "dupe", "route": "/other", "title": "Other", "status": "draft"}
        with self.assertRaises(ActionRequestError):
            cms_helpers.validate_cms_page_payload(payload, None)

    def test_validate_blocks_rejects_unknown_block_type(self):
        with self.assertRaises(ActionRequestError) as cm:
            cms_helpers.validate_cms_blocks([{"block_type": "not_a_real_block", "data": {}}])
        self.assertIn("unknown type 'not_a_real_block'", str(cm.exception))


# ---------------------------------------------------------------------------
# cms/preview.py
# ---------------------------------------------------------------------------
class NormalizeCmsBlocksTests(TestCase):
    def test_non_list_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            normalize_cms_blocks({"not": "a list"})
        self.assertIn("blocks must be a list", str(cm.exception))

    def test_block_not_dict_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            normalize_cms_blocks(["not a dict"])
        self.assertIn("Block #1 must be an object", str(cm.exception))


# ---------------------------------------------------------------------------
# db/cascade.py
# ---------------------------------------------------------------------------
class CascadeImpactTests(TestCase):
    def _make_event_with_tickets(self, ticket_count=2):
        import datetime

        from apps.event.models import Event, Ticket

        event = Event.objects.create(name="Demo Day", date=datetime.date(2025, 6, 15), location="V", description="d")
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


# ---------------------------------------------------------------------------
# cms/actions.py
# ---------------------------------------------------------------------------
class CmsActionTests(SystemIntelligenceActionBase):
    def test_get_cms_page_detail_not_found_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            cms_actions.get_cms_page_detail(slug="missing")
        self.assertIn("CMS page not found", str(cm.exception))

    def test_get_cms_page_detail_returns_serialized_json(self):
        page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")
        result = cms_actions.get_cms_page_detail(page_id=str(page.pk))
        payload = json.loads(result)
        self.assertEqual(payload["title"], "About")
        self.assertEqual(payload["slug"], "about")

    def test_apply_cms_page_update_rejects_non_dict_payload(self):
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            title="Bad payload",
            payload={"page": "not a dict"},
        )
        with self.assertRaises(ActionRequestError) as cm:
            cms_actions.apply_cms_page_update(action)
        self.assertIn("Invalid CMS page action payload", str(cm.exception))


# ---------------------------------------------------------------------------
# context/__init__.py
# ---------------------------------------------------------------------------
class ContextTests(SystemIntelligenceActionBase):
    def test_current_conversation_missing_row_raises(self):
        # Point the context var at a conversation id that does not exist.
        missing_tokens = actions.set_action_context("00000000-0000-0000-0000-000000000000", str(self.admin_user.pk))
        try:
            with self.assertRaises(ActionRequestError) as cm:
                current_conversation()
            self.assertIn("Active chat conversation was not found", str(cm.exception))
        finally:
            actions.reset_action_context(missing_tokens)

    def test_current_user_resolves_set_user(self):
        self.assertEqual(current_user(), self.admin_user)
        self.assertEqual(current_user_id(), str(self.admin_user.pk))

    def test_current_user_returns_none_when_user_missing(self):
        # A syntactically valid UUID that maps to no Member -> DoesNotExist -> None.
        bad_tokens = actions.set_action_context(str(self.conversation.pk), "22222222-2222-2222-2222-222222222222")
        try:
            self.assertIsNone(current_user())
        finally:
            actions.reset_action_context(bad_tokens)

    def test_current_user_returns_none_when_no_user_id_set(self):
        # No user id in context -> early return None without a DB lookup.
        no_user_tokens = actions.set_action_context(str(self.conversation.pk), None)
        try:
            self.assertIsNone(current_user())
        finally:
            actions.reset_action_context(no_user_tokens)


# ---------------------------------------------------------------------------
# orm/records.py
# ---------------------------------------------------------------------------
class OrmRecordsTests(TestCase):
    def test_get_object_missing_raises(self):
        valid_uuid = "11111111-1111-1111-1111-111111111111"
        with self.assertRaises(ActionRequestError) as cm:
            orm_records.get_object(NewsFeedSource, valid_uuid)
        self.assertIn("was not found", str(cm.exception))

    def test_get_object_invalid_pk_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            orm_records.get_object(NewsFeedSource, "not-a-uuid")
        self.assertIn("Invalid primary key", str(cm.exception))

    def test_check_model_permission_requires_staff(self):
        member = Member.objects.create_user(password="testpass123")
        with self.assertRaises(PermissionDenied) as cm:
            orm_records.check_model_permission(member, NewsFeedSource, "view")
        self.assertIn("Staff authentication is required", str(cm.exception))

    def test_check_model_permission_allows_staff_granted_target_app(self):
        # NewsFeedSource lives in the cms app; staff granted "cms" may act on it.
        admin = make_admin(apps=["cms"], email="cms-orm@example.com")
        orm_records.check_model_permission(admin, NewsFeedSource, "change")

    def test_check_model_permission_denies_staff_without_target_app(self):
        # Staff granted a different app is denied for cms models.
        admin = make_admin(apps=["event"], email="event-orm@example.com")
        with self.assertRaises(PermissionDenied) as cm:
            orm_records.check_model_permission(admin, NewsFeedSource, "change")
        self.assertIn("do not have permission", str(cm.exception))


# ---------------------------------------------------------------------------
# comparison/builders.py
# ---------------------------------------------------------------------------
class BuildersTests(TestCase):
    def test_compact_diff_value_summarizes_large_dict(self):
        big = {f"key{i}": "v" * 50 for i in range(20)}
        result = builders.compact_diff_value(big)
        self.assertIn("summary", result)
        self.assertTrue(result["summary"].endswith("..."))
        self.assertEqual(len(result["summary"]), 403)

    def test_block_key_uses_fallback_when_sort_order_not_int(self):
        key = builders.block_key({"sort_order": "abc", "block_type": "rich_text"}, 4)
        self.assertEqual(key, (4, "rich_text", 4))


# ---------------------------------------------------------------------------
# db/actions.py
# ---------------------------------------------------------------------------
class DbActionGuardTests(SystemIntelligenceActionBase):
    def test_propose_db_create_requires_non_empty_fields(self):
        with self.assertRaises(ActionRequestError) as cm:
            actions.propose_db_create("cms", "NewsFeedSource", {})
        self.assertIn("fields must be a non-empty object", str(cm.exception))

    def test_propose_db_update_requires_non_empty_changes(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        with self.assertRaises(ActionRequestError) as cm:
            actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {})
        self.assertIn("changes must be a non-empty object", str(cm.exception))

    def test_apply_db_create_rejects_non_dict_fields(self):
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_CREATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            title="Bad create",
            payload={"fields": "not a dict"},
        )
        from apps.system_intelligence.services.actions.db.actions import apply_db_create

        with self.assertRaises(ActionRequestError) as cm:
            apply_db_create(action, NewsFeedSource)
        self.assertIn("Invalid create payload", str(cm.exception))

    def test_apply_db_update_rejects_non_dict_changes(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        before = orm_records.serialize_model_instance(source, write=True)
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk=str(source.pk),
            title="Bad update",
            payload={"changes": "not a dict"},
            before_snapshot=before,
        )
        from apps.system_intelligence.services.actions.db.actions import apply_db_update

        with self.assertRaises(ActionRequestError) as cm:
            apply_db_update(action, NewsFeedSource)
        self.assertIn("Invalid update payload", str(cm.exception))


# ---------------------------------------------------------------------------
# approval.py
# ---------------------------------------------------------------------------
class ApprovalHelperTests(SystemIntelligenceActionBase):
    def test_safe_error_message_replaces_unknown_exception(self):
        message = approval._safe_error_message(RuntimeError("internal detail"))
        self.assertEqual(message, approval._GENERIC_FAILURE_MESSAGE)

    def test_safe_error_message_passes_through_action_error(self):
        message = approval._safe_error_message(ActionRequestError("user facing"))
        self.assertEqual(message, "user facing")

    def test_sanitize_persisted_message_non_string_returns_generic(self):
        self.assertEqual(approval._sanitize_persisted_message(None), approval._GENERIC_FAILURE_MESSAGE)

    def test_sanitize_strips_control_characters_and_truncates(self):
        cleaned = approval._sanitize_persisted_message("a\x00b\x1fc")
        self.assertEqual(cleaned, "a b c")

    def test_apply_action_unsupported_type_raises(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type="something_unsupported",
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk=str(source.pk),
            title="Unsupported",
        )
        with self.assertRaises(ActionRequestError) as cm:
            approval.apply_action(action, self.admin_user)
        self.assertIn("Unsupported action type: something_unsupported", str(cm.exception))

    def test_unknown_exception_persists_generic_failure_message(self):
        # Drive approve_action_request through the except branch with a non-vetted
        # exception so the persisted error_message is the generic string.
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        response = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": "Renamed"})
        action_id = response["action_request"]["id"]
        with patch(
            "apps.system_intelligence.services.actions.approval.apply_action",
            side_effect=RuntimeError("low level detail"),
        ):
            with self.assertRaises(RuntimeError):
                actions.approve_action_request(action_id, self.admin_user)
        action = SystemIntelligenceActionRequest.objects.get(id=action_id)
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_FAILED)
        self.assertEqual(action.error_message, approval._GENERIC_FAILURE_MESSAGE)


# ---------------------------------------------------------------------------
# utils.py
# ---------------------------------------------------------------------------
class ValidationMessageTests(TestCase):
    def test_message_dict_serialized_as_json(self):
        exc = ValidationError({"title": ["This field is required."]})
        result = utils.validation_message(exc)
        self.assertEqual(json.loads(result), {"title": ["This field is required."]})

    def test_plain_messages_joined(self):
        exc = ValidationError(["First problem.", "Second problem."])
        result = utils.validation_message(exc)
        self.assertEqual(result, "First problem.; Second problem.")


# ---------------------------------------------------------------------------
# comparison/text.py
# ---------------------------------------------------------------------------
class TextHelperTests(TestCase):
    def test_extract_block_text_falls_back_to_json_when_no_text_parts(self):
        # data has no string parts (only numbers) so the text join is empty and
        # the json fallback kicks in.
        block = {"data": {"count": 3, "ratio": 1.5}}
        result = extract_block_text(block)
        self.assertIn('"count": 3', result)

    def test_limit_comparison_text_none_returns_empty_string(self):
        self.assertEqual(limit_comparison_text(None), "")
