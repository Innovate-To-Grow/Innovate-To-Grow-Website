import asyncio
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from django.urls import reverse

from apps.authn.models import (
    Member,
)
from apps.event.tests.helpers import make_admin, make_member
from apps.system_intelligence.services import actions
from apps.system_intelligence.services import tools as system_intelligence_tools
from apps.system_intelligence.services.actions.db.member_guard import ADMIN_STATUS_REFUSED
from apps.system_intelligence.tests.services.actions.guards.test_authn_write_guard import (
    Action,
    AuthnWriteGuardTestCase,
    acting_as,
)

SELF_DELETE_REFUSED = "You cannot delete your own Admin account. Ask another Admin to do it."
SELF_DEACTIVATE_REFUSED = "You cannot deactivate your own Admin account. Ask another Admin to do it."


class MemberWriteTests(AuthnWriteGuardTestCase):
    def test_admin_status_is_not_writable_through_the_assistant(self):
        with acting_as(self.admin), self.assertRaises(actions.ActionRequestError):
            actions.propose_db_update("authn", "Member", str(self.other_admin.pk), {"is_staff": False})
        stored = (
            self.stored_action(self.admin, self.other_admin, {"is_staff": False}),
            self.stored_action(self.admin, self.member, {"is_superuser": True}),
            self.stored(self.admin, Action.ACTION_DB_CREATE, None, {"fields": {"is_staff": True}}, model=Member),
        )
        for action in stored:
            with self.subTest(payload=action.payload), self.assertRaises(actions.ActionRefused):
                actions.approve_action_request(action.pk, self.admin)
            self.assert_failed_with(action, ADMIN_STATUS_REFUSED)

        self.other_admin.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual((self.other_admin.is_staff, self.member.is_staff), (True, False))

    def test_past_the_guard_a_member_create_still_needs_a_password(self):
        # The guard lets a create through; a new member then needs a password, which is never writable, so no one
        # creates members through the assistant.
        action = self.stored(self.admin, Action.ACTION_DB_CREATE, None, {"fields": {"first_name": "New"}}, model=Member)

        with self.assertRaises(ValidationError) as error:
            actions.approve_action_request(action.pk, self.admin)

        self.assertIn("password", error.exception.message_dict)
        action.refresh_from_db()
        self.assertEqual(action.status, Action.STATUS_FAILED)
        self.assertFalse(Member.objects.filter(first_name="New").exists())

    def test_an_admin_cannot_delete_or_deactivate_their_own_account(self):
        with acting_as(self.admin):
            with self.assertRaises(actions.ActionRefused) as deleted:
                actions.propose_db_delete("authn", "Member", str(self.admin.pk))
            for value in (False, "0"):
                with self.subTest(is_active=value):
                    with self.assertRaises(actions.ActionRefused) as deactivated:
                        actions.propose_db_update("authn", "Member", str(self.admin.pk), {"is_active": value})
                    self.assertEqual(str(deactivated.exception), SELF_DEACTIVATE_REFUSED)
        self.assertEqual(str(deleted.exception), SELF_DELETE_REFUSED)
        for action, reason in (
            (self.stored(self.admin, Action.ACTION_DB_DELETE, self.admin, {}), SELF_DELETE_REFUSED),
            (self.stored_action(self.admin, self.admin, {"is_active": False}), SELF_DEACTIVATE_REFUSED),
        ):
            with self.subTest(reason=reason), self.assertRaises(actions.ActionRefused):
                actions.approve_action_request(action.pk, self.admin)
            self.assert_failed_with(action, reason)

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_any_admin_may_change_deactivate_or_delete_another_admin(self):
        third_admin = make_admin(email="third-admin@example.com")
        fourth_admin = make_admin(email="fourth-admin@example.com")
        with acting_as(self.admin):
            proposals = (
                actions.propose_db_update("authn", "Member", str(self.other_admin.pk), {"first_name": "Renamed"}),
                actions.propose_db_update("authn", "Member", str(third_admin.pk), {"is_active": False}),
                actions.propose_db_delete("authn", "Member", str(fourth_admin.pk)),
            )
        for proposal in proposals:
            actions.approve_action_request(proposal["action_request"]["id"], self.admin)

        self.other_admin.refresh_from_db()
        third_admin.refresh_from_db()
        self.assertEqual((self.other_admin.first_name, third_admin.is_active), ("Renamed", False))
        self.assertFalse(Member.objects.filter(pk=fourth_admin.pk).exists())

    def test_member_updates_still_work(self):
        with acting_as(self.admin):
            regular = actions.propose_db_update("authn", "Member", str(self.member.pk), {"title": "Mentor"})
            own = actions.propose_db_update("authn", "Member", str(self.admin.pk), {"title": "Coordinator"})
        for proposal in (regular, own):
            actions.approve_action_request(proposal["action_request"]["id"], self.admin)
        with acting_as(self.admin):
            # Deactivating a regular member, and keeping your own account active, are not lockouts.
            member_off = actions.propose_db_update("authn", "Member", str(self.member.pk), {"is_active": False})
            own_on = actions.propose_db_update("authn", "Member", str(self.admin.pk), {"is_active": True})
        for proposal in (member_off, own_on):
            actions.approve_action_request(proposal["action_request"]["id"], self.admin)

        self.member.refresh_from_db()
        self.admin.refresh_from_db()
        self.assertEqual((self.member.title, self.member.is_active), ("Mentor", False))
        self.assertEqual((self.admin.title, self.admin.is_active), ("Coordinator", True))


class RefusedApprovalViewTests(AuthnWriteGuardTestCase):
    """The chat panel's Approve: a refused change answers with the rule and leaves the request failed, not pending
    behind "Action request not found."."""

    def approve(self, action):
        self.client.force_login(self.admin)
        return self.client.post(reverse("admin:system_intelligence_action_approve", args=[action.pk]))

    def test_a_refused_approval_names_the_rule_and_fails_the_request(self):
        cases = (
            (self.stored(self.admin, Action.ACTION_DB_DELETE, self.admin, {}), SELF_DELETE_REFUSED),
            (self.stored_action(self.admin, self.other_admin, {"is_staff": False}), ADMIN_STATUS_REFUSED),
        )
        for action, reason in cases:
            with self.subTest(reason=reason):
                response = self.approve(action)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], reason)
                self.assertEqual(response.json()["action_request"]["status"], Action.STATUS_FAILED)
                self.assert_failed_with(action, reason)
        self.other_admin.refresh_from_db()
        self.assertTrue(Member.objects.filter(pk=self.admin.pk).exists())
        self.assertTrue(self.other_admin.is_staff)

    def test_a_refusal_without_a_stored_reason_still_names_no_missing_request(self):
        # Should the failed approval not have stored its reason (the request changed meanwhile), the answer is still
        # a refusal, not "Action request not found.".
        action = self.stored_action(self.admin, self.other_admin, {"first_name": "Renamed"})
        with patch.object(actions, "approve_action_request", side_effect=actions.ActionRefused(ADMIN_STATUS_REFUSED)):
            response = self.approve(action)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "You may not make this change.")


class MemberUpdateToolTests(TransactionTestCase):
    """propose_member_update (the assistant's tool) still proposes allowed changes and reports a refusal."""

    def test_allowed_changes_are_proposed_and_refusals_reported(self):
        cache.clear()
        admin = make_admin(email="admin@example.com")
        other_admin = make_admin(email="other-admin@example.com", first_name="Other")
        member = make_member(email="member@example.com", first_name="Ada", last_name="Member")
        with acting_as(admin):
            proposed = asyncio.run(system_intelligence_tools.propose_member_update(str(member.pk), {"title": "Mentor"}))
            other = asyncio.run(
                system_intelligence_tools.propose_member_update(str(other_admin.pk), {"first_name": "Renamed"})
            )
            refused = asyncio.run(system_intelligence_tools.propose_member_update(str(admin.pk), {"is_active": False}))

        self.assertEqual(proposed["action_request"]["status"], Action.STATUS_PENDING)
        self.assertEqual(other["action_request"]["status"], Action.STATUS_PENDING)
        self.assertIn(f"Tool error: {SELF_DEACTIVATE_REFUSED}", refused["result"])
        self.assertTrue(Member.objects.filter(pk=admin.pk, is_active=True).exists())
