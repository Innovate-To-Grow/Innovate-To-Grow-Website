"""Tests for BaseModelAdmin / ReadOnlyModelAdmin and the LogEntry admin."""

from unittest.mock import MagicMock, patch

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.authn.models import Member
from apps.core.admin.base import BaseModelAdmin, ReadOnlyModelAdmin
from apps.core.admin.log_entry import LogEntryAdmin
from apps.event.tests.helpers import make_superuser


class BaseModelAdminPermissionTest(TestCase):
    def setUp(self):
        self.admin = BaseModelAdmin(LogEntry, AdminSite())
        self.user = Member.objects.create_user(password="testpass123", is_staff=True, is_superuser=False)
        self.request = MagicMock()
        self.request.user = self.user

    def test_staff_without_model_permissions_is_not_granted_admin_access(self):
        self.assertFalse(self.admin.has_module_permission(self.request))
        self.assertFalse(self.admin.has_view_permission(self.request))
        self.assertFalse(self.admin.has_add_permission(self.request))
        self.assertFalse(self.admin.has_change_permission(self.request))
        self.assertFalse(self.admin.has_delete_permission(self.request))


class ReadOnlyModelAdminTest(TestCase):
    def setUp(self):
        self.admin = LogEntryAdmin(LogEntry, AdminSite())

    def test_is_read_only_admin(self):
        self.assertIsInstance(self.admin, ReadOnlyModelAdmin)

    def test_get_actions_removes_delete_selected(self):
        """ReadOnlyModelAdmin.get_actions strips delete_selected when present."""
        request = MagicMock()
        request.user = make_superuser()
        # Force the parent chain to return a dict that includes delete_selected so
        # the `del actions["delete_selected"]` branch executes.
        with patch(
            "apps.core.admin.base.BaseModelAdmin.get_actions",
            return_value={"delete_selected": ("f", "delete_selected", "Delete"), "export_data": ("g", "x", "y")},
        ):
            actions = self.admin.get_actions(request)
        self.assertNotIn("delete_selected", actions)
        self.assertIn("export_data", actions)

    def test_permission_methods_all_false(self):
        request = MagicMock()
        self.assertFalse(self.admin.has_add_permission(request))
        self.assertFalse(self.admin.has_change_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request))


class LogEntryAdminTest(TestCase):
    def setUp(self):
        self.admin = LogEntryAdmin(LogEntry, AdminSite())

    def test_action_flag_display_returns_human_label(self):
        user = make_superuser()
        entry = LogEntry.objects.create(
            user=user,
            content_type=ContentType.objects.get_for_model(LogEntry),
            object_id="1",
            object_repr="Some object",
            action_flag=ADDITION,
            change_message="added",
        )
        self.assertEqual(self.admin.action_flag_display(entry), entry.get_action_flag_display())
        self.assertEqual(self.admin.action_flag_display(entry), "Addition")
