"""Coverage for embed_sections normalization helpers and effective-section fallback."""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSEmbedWidget, CMSPage
from apps.cms.services.embed import (
    effective_hidden_sections,
    hidden_section_presets_payload,
    normalize_hidden_sections,
)


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

    def test_section_titles_names_the_project_page_header_it_hides(self):
        # The project app routes have no `.section-title`; the preset hides their marked page header.
        by_key = {preset["key"]: preset for preset in hidden_section_presets_payload()}
        self.assertEqual(by_key["section_titles"]["label"], "Section titles and page header")
        for route in ("/current-projects", "/presenting-teams", "/past-projects", "/all-projects"):
            self.assertEqual(normalize_hidden_sections(["section_titles"], "app_route", route), ["section_titles"])


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

    def test_all_projects_widget_can_hide_its_page_header(self):
        # /all-projects is an embeddable app route, and marks its header for "Section titles and page header".
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="all-projects",
            app_route="/all-projects",
            hidden_sections=["section_titles"],
        )
        widget.full_clean()
        self.assertEqual(effective_hidden_sections(widget), ["section_titles"])

    def test_non_list_stored_sections_default_to_empty(self):
        widget = CMSEmbedWidget(
            widget_type="blocks",
            slug="nonlist",
            hidden_sections="oops not a list",
            hide_section_titles=False,
        )
        self.assertEqual(effective_hidden_sections(widget), [])
