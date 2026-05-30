"""Coverage for embed_sections normalization helpers and effective-section fallback."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.cms.embed_sections import effective_hidden_sections, normalize_hidden_sections
from apps.cms.models import CMSEmbedWidget, CMSPage


class NormalizeHiddenSectionsTests(SimpleTestCase):
    def test_none_value_treated_as_empty(self):
        self.assertEqual(normalize_hidden_sections(None, "blocks", ""), [])

    def test_empty_string_value_treated_as_empty(self):
        self.assertEqual(normalize_hidden_sections("", "blocks", ""), [])

    def test_non_list_value_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            normalize_hidden_sections(42, "blocks", "")
        self.assertIn("must be a list", ctx.exception.messages[0])

    def test_dedupes_and_orders_known_keys(self):
        result = normalize_hidden_sections(
            ["schedule_projects", "section_titles", "schedule_projects"],
            "app_route",
            "/schedule",
        )
        # section_titles is ordered before schedule_projects per preset order.
        self.assertEqual(result, ["section_titles", "schedule_projects"])

    def test_unavailable_key_for_route_raises(self):
        with self.assertRaises(ValidationError):
            normalize_hidden_sections(["schedule_projects"], "app_route", "/news")


class EffectiveHiddenSectionsTests(TestCase):
    def test_legacy_hide_flag_adds_section_titles(self):
        widget = CMSEmbedWidget(
            widget_type="blocks",
            slug="legacy",
            hidden_sections=[],
            hide_section_titles=True,
        )
        self.assertEqual(effective_hidden_sections(widget), ["section_titles"])

    def test_invalid_stored_sections_fall_back_to_filtered_subset(self):
        page = CMSPage.objects.create(slug="h", route="/h", title="H", status="draft")
        # Store a section key that is invalid for a blocks widget. normalize raises,
        # so the fallback filters to only the keys that remain allowed.
        widget = CMSEmbedWidget(
            widget_type="blocks",
            slug="fallback",
            page=page,
            hidden_sections=["section_titles", "schedule_projects"],
            hide_section_titles=False,
        )
        result = effective_hidden_sections(widget)
        # schedule_projects is dropped (not allowed for blocks), section_titles kept.
        self.assertEqual(result, ["section_titles"])

    def test_non_list_stored_sections_default_to_empty(self):
        widget = CMSEmbedWidget(
            widget_type="blocks",
            slug="nonlist",
            hidden_sections="oops not a list",
            hide_section_titles=False,
        )
        self.assertEqual(effective_hidden_sections(widget), [])
