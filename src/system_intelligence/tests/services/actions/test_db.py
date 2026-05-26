from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied

from authn.models import Member
from cms.models import CMSPage, Menu
from system_intelligence.models import SystemIntelligenceActionRequest
from system_intelligence.services import actions

from .base import SystemIntelligenceActionBase


class SystemIntelligenceDBActionTests(SystemIntelligenceActionBase):
    def test_db_update_proposal_is_single_record_and_requires_approval(self):
        menu = Menu.objects.create(
            name="ucm", display_name="UC Merced", items=[{"title": "Home", "url": "/"}], is_active=True
        )
        response = actions.propose_db_update(
            "cms",
            "Menu",
            str(menu.pk),
            {"display_name": "Updated Source", "is_active": False},
            summary="Update menu display name.",
        )
        menu.refresh_from_db()
        self.assertEqual(menu.display_name, "UC Merced")
        action = actions.approve_action_request(response["action_request"]["id"], self.admin_user)
        menu.refresh_from_db()
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_APPLIED)
        self.assertEqual(menu.display_name, "Updated Source")
        self.assertFalse(menu.is_active)
        comparison = response["action_request"]["comparison"]
        self.assertEqual(comparison["type"], "db_record")
        self.assertEqual(comparison["mode"], "update")
        is_active_row = next(row for row in comparison["fields"] if row["field"] == "is_active")
        self.assertEqual(is_active_row["before_display"], "Yes")
        self.assertEqual(is_active_row["after_display"], "No")

    def test_db_create_and_delete_proposals_apply_after_approval(self):
        create_response = actions.propose_db_create(
            "cms",
            "Menu",
            {"name": "new-feed", "display_name": "New Feed", "items": [{"title": "Home", "url": "/"}]},
        )
        self.assertFalse(Menu.objects.filter(name="new-feed").exists())
        create_action = actions.approve_action_request(create_response["action_request"]["id"], self.admin_user)
        created = Menu.objects.get(name="new-feed")
        self.assertEqual(create_action.target_pk, str(created.pk))
        delete_response = actions.propose_db_delete("cms", "Menu", str(created.pk))
        actions.approve_action_request(delete_response["action_request"]["id"], self.admin_user)
        self.assertFalse(Menu.objects.filter(pk=created.pk).exists())

    def test_db_write_rejects_sensitive_fields_and_cms_page_bypass(self):
        member = Member.objects.create_user(password="testpass123")
        with self.assertRaises(actions.ActionRequestError):
            actions.propose_db_update("authn", "Member", str(member.pk), {"password": "new-pass"})
        page = CMSPage.objects.create(slug="home", route="/home", title="Home", status="draft")
        with self.assertRaises(actions.ActionRequestError):
            actions.propose_db_update("cms", "CMSPage", str(page.pk), {"title": "Bypass Preview"})

    def test_reject_action_does_not_mutate_record(self):
        menu = Menu.objects.create(
            name="ucm", display_name="UC Merced", items=[{"title": "Home", "url": "/"}], is_active=True
        )
        response = actions.propose_db_update("cms", "Menu", str(menu.pk), {"display_name": "Rejected"})
        action = actions.reject_action_request(response["action_request"]["id"], self.admin_user)
        menu.refresh_from_db()
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_REJECTED)
        self.assertEqual(menu.display_name, "UC Merced")

    def test_approve_fails_when_target_changed_after_proposal(self):
        menu = Menu.objects.create(
            name="ucm", display_name="UC Merced", items=[{"title": "Home", "url": "/"}], is_active=True
        )
        response = actions.propose_db_update("cms", "Menu", str(menu.pk), {"display_name": "Approved"})
        menu.display_name = "Changed elsewhere"
        menu.save()
        with self.assertRaises(actions.ActionRequestError):
            actions.approve_action_request(response["action_request"]["id"], self.admin_user)
        menu.refresh_from_db()
        action = SystemIntelligenceActionRequest.objects.get(id=response["action_request"]["id"])
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_FAILED)
        self.assertEqual(menu.display_name, "Changed elsewhere")

    def test_permission_denied_on_approve_keeps_action_pending(self):
        menu = Menu.objects.create(
            name="ucm", display_name="UC Merced", items=[{"title": "Home", "url": "/"}], is_active=True
        )
        response = actions.propose_db_update("cms", "Menu", str(menu.pk), {"display_name": "Approved"})
        narrow_user = Member.objects.create_user(password="narrowpass")
        narrow_user.is_staff = True
        narrow_user.save(update_fields=["is_staff"])
        narrow_user.user_permissions.add(Permission.objects.get(codename="view_menu", content_type__app_label="cms"))
        with self.assertRaises(PermissionDenied):
            actions.approve_action_request(response["action_request"]["id"], narrow_user)
        action = SystemIntelligenceActionRequest.objects.get(id=response["action_request"]["id"])
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_PENDING)
        menu.refresh_from_db()
        self.assertEqual(menu.display_name, "UC Merced")
