import datetime
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from apps.cms.models import CMSPage, NewsFeedSource
from apps.cms.models.content.news.article import NewsArticle
from apps.system_intelligence.services.actions.cms import helpers as cms_helpers
from apps.system_intelligence.services.actions.cms.preview import normalize_cms_blocks
from apps.system_intelligence.services.actions.comparison import field_display as fd
from apps.system_intelligence.services.actions.exceptions import ActionRequestError


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
