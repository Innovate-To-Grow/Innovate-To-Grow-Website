"""Tests for SiteSettings model: singleton pattern, homepage route fallback logic."""

from django.test import TestCase

from cms.models import CMSPage, SiteSettings


class SiteSettingsSingletonTests(TestCase):
    def test_save_enforces_pk_1(self):
        s = SiteSettings()
        s.save()
        self.assertEqual(s.pk, 1)

    def test_multiple_saves_same_row(self):
        SiteSettings().save()
        SiteSettings().save()
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_load_creates_if_missing(self):
        self.assertEqual(SiteSettings.objects.count(), 0)
        s = SiteSettings.load()
        self.assertIsNotNone(s)
        self.assertEqual(s.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_load_returns_existing(self):
        SiteSettings.objects.create()
        s = SiteSettings.load()
        self.assertEqual(s.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_str(self):
        s = SiteSettings()
        self.assertEqual(str(s), "Site Settings")


class SiteSettingsHomepageRouteTests(TestCase):
    def test_no_pages_returns_slash(self):
        s = SiteSettings.load()
        self.assertEqual(s.get_homepage_route(), "/")

    def test_selected_published_page_returns_its_route(self):
        page = CMSPage.objects.create(slug="home", route="/home", title="Home", status="published")
        s = SiteSettings.load()
        s.homepage_page = page
        s.save()
        self.assertEqual(s.get_homepage_route(), "/home")

    def test_selected_draft_page_falls_back_to_root(self):
        draft = CMSPage.objects.create(slug="draft", route="/draft", title="Draft", status="draft")
        root = CMSPage.objects.create(slug="root", route="/", title="Root", status="published")
        s = SiteSettings.load()
        s.homepage_page = draft
        s.save()
        self.assertEqual(s.get_homepage_route(), root.route)

    def test_selected_archived_page_falls_back_to_root(self):
        archived = CMSPage.objects.create(slug="old", route="/old", title="Old", status="archived")
        root = CMSPage.objects.create(slug="root", route="/", title="Root", status="published")
        s = SiteSettings.load()
        s.homepage_page = archived
        s.save()
        self.assertEqual(s.get_homepage_route(), root.route)

    def test_no_selected_page_uses_root_page(self):
        root = CMSPage.objects.create(slug="root", route="/", title="Root", status="published")
        s = SiteSettings.load()
        self.assertEqual(s.get_homepage_route(), root.route)

    def test_no_selected_and_root_draft_returns_slash(self):
        CMSPage.objects.create(slug="root", route="/", title="Root", status="draft")
        s = SiteSettings.load()
        self.assertEqual(s.get_homepage_route(), "/")

    def test_selected_page_deleted_falls_back(self):
        page = CMSPage.objects.create(slug="del", route="/del", title="Del", status="published")
        root = CMSPage.objects.create(slug="root", route="/", title="Root", status="published")
        s = SiteSettings.load()
        s.homepage_page = page
        s.save()

        page.delete()
        s.refresh_from_db()
        self.assertEqual(s.get_homepage_route(), root.route)
