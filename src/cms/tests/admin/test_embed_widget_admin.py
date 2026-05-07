"""Tests for the standalone CMSEmbedWidget admin module."""

from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from authn.models import ContactEmail
from cms.admin.cms.cms_embed_widget import CMSEmbedWidgetAdminForm
from cms.models import CMSBlock, CMSEmbedWidget, CMSPage

Member = get_user_model()


class CMSEmbedWidgetModelTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.page = CMSPage.objects.create(
            slug="host",
            route="/host",
            title="Host",
            status="draft",
        )
        for i in range(3):
            CMSBlock.objects.create(
                page=self.page,
                block_type="rich_text",
                sort_order=i,
                data={"body_html": f"<p>Block {i}</p>"},
            )

    def _full_clean(self, **kwargs):
        widget = CMSEmbedWidget(page=self.page, **kwargs)
        widget.full_clean()
        return widget

    def test_clean_requires_slug(self):
        with self.assertRaises(ValidationError) as ctx:
            self._full_clean(slug="", block_sort_orders=[0])
        self.assertIn("slug", ctx.exception.message_dict)

    def test_clean_rejects_invalid_slug_format(self):
        for bad in ("has space", "-leading", "punct!"):
            with self.assertRaises(ValidationError, msg=f"{bad!r} should fail"):
                self._full_clean(slug=bad, block_sort_orders=[0])

    def test_clean_lowercases_slug(self):
        widget = self._full_clean(slug="Mixed-CASE", block_sort_orders=[0])
        self.assertEqual(widget.slug, "mixed-case")

    def test_clean_requires_valid_block_reference(self):
        with self.assertRaises(ValidationError) as ctx:
            self._full_clean(slug="w1", block_sort_orders=[99])
        self.assertIn("block_sort_orders", ctx.exception.message_dict)

    def test_clean_deduplicates_and_sorts_block_refs(self):
        widget = self._full_clean(slug="w2", block_sort_orders=[2, 0, 2, 1])
        self.assertEqual(widget.block_sort_orders, [0, 1, 2])

    def test_clean_drops_non_integer_refs(self):
        widget = self._full_clean(slug="w3", block_sort_orders=[0, "x", None, 2])
        self.assertEqual(widget.block_sort_orders, [0, 2])

    def test_clean_rejects_no_valid_refs(self):
        with self.assertRaises(ValidationError):
            self._full_clean(slug="w4", block_sort_orders=["nope"])

    def test_app_route_widget_requires_app_route(self):
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed")
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("app_route", ctx.exception.message_dict)

    def test_app_route_widget_rejects_unknown_route(self):
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed", app_route="/nope")
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("app_route", ctx.exception.message_dict)

    def test_app_route_widget_clears_block_sort_orders(self):
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="app-embed",
            app_route="/schedule",
            block_sort_orders=[0, 1, 2],
        )
        widget.full_clean()
        self.assertEqual(widget.block_sort_orders, [])
        self.assertEqual(widget.app_route, "/schedule")

    def test_app_route_widget_does_not_require_page(self):
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed", app_route="/schedule")
        widget.full_clean()
        self.assertIsNone(widget.page_id)

    def test_blocks_widget_requires_page(self):
        widget = CMSEmbedWidget(widget_type="blocks", slug="bw", block_sort_orders=[0])
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("page", ctx.exception.message_dict)

    def test_slug_is_globally_unique_at_db_level(self):
        CMSEmbedWidget.objects.create(page=self.page, slug="shared", block_sort_orders=[0])
        other = CMSPage.objects.create(slug="other", route="/other", title="Other", status="draft")
        CMSBlock.objects.create(page=other, block_type="rich_text", sort_order=0, data={})
        with self.assertRaises(IntegrityError):
            CMSEmbedWidget.objects.create(page=other, slug="shared", block_sort_orders=[0])

    def test_hide_section_titles_default_false(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="default-hide-flag", block_sort_orders=[0])
        widget.refresh_from_db()
        self.assertFalse(widget.hide_section_titles)

    def test_hide_section_titles_roundtrips_when_set_true(self):
        widget = CMSEmbedWidget.objects.create(
            page=self.page,
            slug="enabled-hide-flag",
            block_sort_orders=[0],
            hide_section_titles=True,
        )
        widget.refresh_from_db()
        self.assertTrue(widget.hide_section_titles)

    def test_hidden_sections_default_empty(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="default-hidden-sections", block_sort_orders=[0])
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, [])

    def test_clean_normalizes_hidden_sections_and_legacy_flag(self):
        widget = self._full_clean(slug="hide-section-title", block_sort_orders=[0], hidden_sections=["section_titles"])
        self.assertEqual(widget.hidden_sections, ["section_titles"])
        self.assertTrue(widget.hide_section_titles)

    def test_clean_rejects_route_incompatible_hidden_sections(self):
        with self.assertRaises(ValidationError) as ctx:
            self._full_clean(slug="bad-schedule-hide", block_sort_orders=[0], hidden_sections=["schedule_projects"])
        self.assertIn("hidden_sections", ctx.exception.message_dict)

    def test_app_route_widget_accepts_schedule_hidden_sections(self):
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="schedule-sections",
            app_route="/schedule",
            hidden_sections=["schedule_projects", "section_titles"],
        )
        widget.full_clean()
        self.assertEqual(widget.hidden_sections, ["section_titles", "schedule_projects"])

    def test_migration_copies_legacy_hide_title_flag(self):
        widget = CMSEmbedWidget.objects.create(
            page=self.page,
            slug="legacy-title-hide",
            block_sort_orders=[0],
            hide_section_titles=True,
            hidden_sections=[],
        )
        migration = import_module("cms.migrations.0012_cmsembedwidget_hidden_sections")
        migration.migrate_hide_section_titles(apps, None)
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, ["section_titles"])


class CMSEmbedWidgetAdminFormTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.page = CMSPage.objects.create(slug="host", route="/host", title="Host", status="draft")
        for i in range(2):
            CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=i, data={})

    def test_form_valid_with_hidden_block_sort_orders(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "valid-widget",
                "admin_label": "Valid",
                "block_sort_orders": "[0, 1]",
                "app_route": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        self.assertEqual(widget.slug, "valid-widget")
        self.assertEqual(widget.widget_type, "blocks")
        self.assertEqual(widget.block_sort_orders, [0, 1])

    def test_form_rejects_invalid_slug(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "Bad Slug",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("slug", form.errors)

    def test_form_valid_for_app_route_widget(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "schedule-embed",
                "admin_label": "Schedule",
                "block_sort_orders": "[]",
                "app_route": "/schedule",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        self.assertEqual(widget.widget_type, "app_route")
        self.assertEqual(widget.app_route, "/schedule")
        self.assertIsNone(widget.page_id)
        self.assertEqual(widget.block_sort_orders, [])

    def test_form_rejects_app_route_widget_with_unknown_route(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "app-embed",
                "admin_label": "",
                "block_sort_orders": "[]",
                "app_route": "/unknown",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("app_route", form.errors)

    def test_form_persists_hidden_sections(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "hide-sections-on",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
                "hidden_sections": ["section_titles"],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, ["section_titles"])
        self.assertTrue(widget.hide_section_titles)

    def test_form_persists_route_specific_hidden_sections(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "schedule-hidden-sections",
                "admin_label": "",
                "block_sort_orders": "[]",
                "app_route": "/schedule",
                "hidden_sections": ["schedule_header", "schedule_projects"],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, ["schedule_header", "schedule_projects"])
        self.assertFalse(widget.hide_section_titles)

    def test_form_rejects_route_incompatible_hidden_sections(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "news-hidden-sections",
                "admin_label": "",
                "block_sort_orders": "[]",
                "app_route": "/news",
                "hidden_sections": ["schedule_projects"],
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("hidden_sections", form.errors)

    def test_form_defaults_hidden_sections_empty_when_omitted(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "hide-sections-off",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
                # hidden_sections intentionally omitted — no checkbox selected
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, [])
        self.assertFalse(widget.hide_section_titles)


class CMSEmbedWidgetAdminViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Embed",
            last_name="Admin",
        )
        ContactEmail.objects.create(
            member=self.admin_user,
            email_address="admin@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.login(username="admin@example.com", password="testpass123")
        self.page = CMSPage.objects.create(slug="host", route="/host", title="Host", status="draft")
        for i in range(2):
            CMSBlock.objects.create(
                page=self.page,
                block_type="rich_text",
                sort_order=i,
                admin_label=f"Block {i}",
                data={},
            )

    def test_changelist_renders(self):
        response = self.client.get(reverse("admin:cms_cmsembedwidget_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_add_form_renders(self):
        response = self.client.get(reverse("admin:cms_cmsembedwidget_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Embed URL")
        self.assertContains(response, 'id="cms-widget-app-route-status"')
        self.assertContains(response, "Sections to hide")
        self.assertContains(response, "schedule_projects")
        self.assertContains(response, "cms/js/cms-embed-widget/previews.js")

    def test_add_form_replaces_legacy_hide_toggle_with_hidden_section_presets(self):
        response = self.client.get(reverse("admin:cms_cmsembedwidget_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="hidden_sections"')
        self.assertContains(response, 'value="section_titles"')
        self.assertContains(response, 'value="schedule_projects"')
        self.assertContains(response, "hiddenSectionPresets")
        self.assertNotContains(response, 'name="hide_section_titles"')

    def test_page_blocks_endpoint_returns_blocks(self):
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        response = self.client.get(url, {"page_id": str(self.page.pk)})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["blocks"]), 2)
        self.assertEqual(payload["blocks"][0]["sort_order"], 0)
        self.assertEqual(payload["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(payload["blocks"][0]["admin_label"], "Block 0")

    def test_page_blocks_endpoint_empty_without_page_id(self):
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"blocks": []})

    def test_page_blocks_endpoint_requires_staff(self):
        self.client.logout()
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        response = self.client.get(url, {"page_id": str(self.page.pk)})
        # Admin view redirects to login for anonymous users.
        self.assertIn(response.status_code, (302, 403))

    def test_app_routes_endpoint_returns_routes(self):
        url = reverse("admin:cms_cmsembedwidget_app_routes")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        urls = [r["url"] for r in payload["routes"]]
        self.assertIn("/schedule", urls)
        self.assertIn("/presenting-teams", urls)

    def test_app_routes_endpoint_requires_staff(self):
        self.client.logout()
        url = reverse("admin:cms_cmsembedwidget_app_routes")
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403))
