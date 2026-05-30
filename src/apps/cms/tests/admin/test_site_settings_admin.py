"""Tests for the SiteSettings admin: homepage form, display columns, cache busting on save."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.cms.admin.layout.site_settings import SiteSettingsAdmin, SiteSettingsForm
from apps.cms.models import CMSPage, SiteSettings


class SiteSettingsFormTests(TestCase):
    def setUp(self):
        self.published = CMSPage.objects.create(slug="home", route="/home", title="Home", status="published")
        self.draft = CMSPage.objects.create(slug="draft", route="/draft", title="Draft", status="draft")

    def test_queryset_limited_to_published_pages(self):
        form = SiteSettingsForm()
        qs = form.fields["homepage_page"].queryset
        self.assertIn(self.published, qs)
        self.assertNotIn(self.draft, qs)
        # The styling class for Unfold controls is applied.
        self.assertIn("border-base-200", form.fields["homepage_page"].widget.attrs["class"])

    def test_queryset_includes_current_selection_even_if_unpublished(self):
        settings_obj = SiteSettings.load()
        # Assign a draft page directly so the form must surface it in the queryset.
        settings_obj.homepage_page = self.draft
        settings_obj.save()

        form = SiteSettingsForm(instance=settings_obj)
        qs = form.fields["homepage_page"].queryset
        self.assertIn(self.draft, qs)
        self.assertIn(self.published, qs)

    def test_clean_homepage_page_accepts_published(self):
        form = SiteSettingsForm(data={"homepage_page": str(self.published.pk), "design_tokens": '{"colors": {}}'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["homepage_page"], self.published)

    def test_clean_homepage_page_rejects_unpublished(self):
        # Force a draft page into the queryset so field validation passes and
        # clean_homepage_page is the gate that rejects it.
        settings_obj = SiteSettings.load()
        settings_obj.homepage_page = self.draft
        settings_obj.save()

        form = SiteSettingsForm(
            instance=settings_obj,
            data={"homepage_page": str(self.draft.pk), "design_tokens": '{"colors": {}}'},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("homepage_page", form.errors)
        self.assertIn("published CMS page", form.errors["homepage_page"][0])

    def test_clean_homepage_page_allows_empty(self):
        form = SiteSettingsForm(data={"design_tokens": '{"colors": {}}'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["homepage_page"])


class SiteSettingsAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = SiteSettingsAdmin(SiteSettings, AdminSite())
        self.page = CMSPage.objects.create(slug="home", route="/home", title="Home", status="published")

    def test_homepage_page_display_with_page(self):
        settings_obj = SiteSettings.load()
        settings_obj.homepage_page = self.page
        settings_obj.save()
        self.assertEqual(self.admin.homepage_page_display(settings_obj), "Home (/home)")

    def test_homepage_page_display_fallback(self):
        settings_obj = SiteSettings.load()
        self.assertEqual(self.admin.homepage_page_display(settings_obj), "Fallback to /")

    def test_homepage_route_display_delegates_to_model(self):
        settings_obj = SiteSettings.load()
        settings_obj.homepage_page = self.page
        settings_obj.save()
        self.assertEqual(self.admin.homepage_route_display(settings_obj), "/home")


class SiteSettingsAdminSaveTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = SiteSettingsAdmin(SiteSettings, AdminSite())

    def test_save_model_busts_layout_cache(self):
        settings_obj = SiteSettings.load()
        request = self.factory.post("/admin/cms/sitesettings/")

        with patch("apps.cms.admin.layout.site_settings.cache") as mock_cache:
            self.admin.save_model(request, settings_obj, form=None, change=True)
            mock_cache.delete.assert_called_once_with("layout:data")

    def test_has_add_permission_blocked_once_singleton_exists(self):
        request = self.factory.get("/admin/cms/sitesettings/")
        self.assertTrue(self.admin.has_add_permission(request))
        SiteSettings.objects.create()
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_delete_permission_always_false(self):
        request = self.factory.get("/admin/cms/sitesettings/")
        self.assertFalse(self.admin.has_delete_permission(request))
