from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.projects.admin.past_project_share import PastProjectShareAdmin
from apps.projects.models import PastProjectShare

User = get_user_model()


def _make_superuser(email="admin@example.com"):
    user = User.objects.create_superuser(password="testpass123", first_name="Admin", last_name="User")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


class PastProjectShareAdminTest(TestCase):
    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.model_admin = PastProjectShareAdmin(PastProjectShare, admin.site)
        self.share = PastProjectShare.objects.create(
            name="Finalists",
            rows=[{"project_title": "X"}, {"project_title": "Y"}],
            created_by=self.admin_user,
        )

    def test_changelist_renders(self):
        response = self.client.get(reverse("admin:projects_pastprojectshare_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finalists")

    def test_change_view_is_read_only(self):
        response = self.client.get(reverse("admin:projects_pastprojectshare_change", args=[self.share.pk]))
        self.assertEqual(response.status_code, 200)

    def test_view_and_delete_only_permissions(self):
        self.assertFalse(self.model_admin.has_add_permission(request=None))
        self.assertFalse(self.model_admin.has_change_permission(request=None))
        self.assertTrue(self.model_admin.has_delete_permission(self._staff_request()))

    def test_row_count_and_rows_preview(self):
        self.assertEqual(self.model_admin.row_count(self.share), 2)
        preview = str(self.model_admin.rows_preview(self.share))
        self.assertIn("<pre", preview)
        self.assertIn("project_title", preview)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_delete_view_removes_share(self):
        response = self.client.post(
            reverse("admin:projects_pastprojectshare_delete", args=[self.share.pk]),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PastProjectShare.objects.filter(pk=self.share.pk).exists())

    def test_str_falls_back_when_name_blank(self):
        legacy = PastProjectShare.objects.create(name="", rows=[])
        self.assertEqual(str(legacy), f"Project Resource Share {legacy.pk}")

    def _staff_request(self):
        class _Req:
            user = self.admin_user

        return _Req()
