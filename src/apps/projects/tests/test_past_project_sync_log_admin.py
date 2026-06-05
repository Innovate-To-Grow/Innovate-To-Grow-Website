from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.projects.admin.past_project_sync_log import PastProjectSyncLogAdmin
from apps.projects.models import PastProjectsSheetConfig, PastProjectSyncLog

User = get_user_model()


def _make_superuser(email="admin@example.com"):
    user = User.objects.create_superuser(password="testpass123", first_name="Admin", last_name="User")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


class PastProjectSyncLogAdminTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.model_admin = PastProjectSyncLogAdmin(PastProjectSyncLog, admin.site)
        self.config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)

    def test_is_read_only(self):
        self.assertFalse(self.model_admin.has_add_permission(request=None))
        self.assertFalse(self.model_admin.has_change_permission(request=None))
        self.assertFalse(self.model_admin.has_delete_permission(request=None))

    def test_changelist_renders_log_row(self):
        PastProjectSyncLog.objects.create(
            config=self.config,
            sync_type=PastProjectSyncLog.SyncType.MANUAL,
            status=PastProjectSyncLog.Status.SUCCESS,
            projects_created=7,
        )
        response = self.client.get(reverse("admin:projects_pastprojectsynclog_changelist"))
        self.assertEqual(response.status_code, 200)
