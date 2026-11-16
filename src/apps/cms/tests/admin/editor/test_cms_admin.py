from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.admin.cms.cms_page import CMSPageAdminForm
from apps.cms.models import CMSPage

Member = get_user_model()


class _MessageCollector:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, request, message):
        self.errors.append(message)

    def warning(self, request, message):
        self.warnings.append(message)


class CMSPageAdminFormTests(TestCase):
    # noinspection PyMethodMayBeStatic
    def build_form_data(self, **overrides):
        data = {
            "slug": "cms-admin-test",
            "route": "/cms-admin-test/",
            "title": "CMS Admin Test",
            "meta_description": "",
            "page_css_class": "",
            "status": "draft",
            "sort_order": 0,
            "published_at": "",
        }
        data.update(overrides)
        return data

    def test_route_form_normalizes_trailing_slash(self):
        form = CMSPageAdminForm(data=self.build_form_data(route="/about/"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["route"], "/about")

    def test_route_form_rejects_conflict_after_normalization(self):
        CMSPage.objects.create(
            slug="existing-route",
            route="/event/live",
            title="Existing Route",
            status="published",
        )

        form = CMSPageAdminForm(
            data=self.build_form_data(
                slug="conflicting-route",
                route="//event//live/",
                title="Conflicting Route",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("route", form.errors)
        self.assertIn("already used", form.errors["route"][0])


class CMSPageAdminViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Route",
            last_name="Admin",
        )
        ContactEmail.objects.create(
            member=self.admin_user, email_address="admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="admin@example.com", password="testpass123")

    def test_route_conflict_endpoint_reports_conflict(self):
        page = CMSPage.objects.create(
            slug="existing-homepage",
            route="/home-during-event",
            title="Existing Homepage",
            status="published",
        )

        response = self.client.get(
            reverse("admin:cms_cmspage_route_conflict"),
            {"route": "//home-during-event/", "page_id": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["normalized_route"], page.route)
        self.assertTrue(response.json()["has_conflict"])
