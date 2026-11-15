import asyncio
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from django.urls import reverse

from apps.authn.models import (
    Member,
)
from apps.event.tests.helpers import make_admin, make_member, make_superuser
from apps.system_intelligence.services import actions
from apps.system_intelligence.services import tools as system_intelligence_tools
from apps.system_intelligence.tests.services.actions.guards.test_authn_write_guard import (
    SECTIONS_REFUSED,
    TARGET_REFUSED,
    Action,
    AuthnWriteGuardTestCase,
    acting_as,
)


class MemberWriteTests(AuthnWriteGuardTestCase):
    def test_a_non_superuser_cannot_grant_admin_sections(self):
        for target in (self.staffer, self.member):
            with self.subTest(target=target.first_name), acting_as(self.staffer):
                with self.assertRaises(actions.ActionRefused) as error:
                    actions.propose_db_update("authn", "Member", str(target.pk), {"admin_apps": ["core", "cms"]})
                self.assertEqual(str(error.exception), SECTIONS_REFUSED)
        with acting_as(self.staffer), self.assertRaises(actions.ActionRefused):
            actions.propose_db_create("authn", "Member", {"first_name": "New", "admin_apps": ["core"]})

        self.staffer.refresh_from_db()
        self.assertEqual(self.staffer.admin_apps, ["authn", "system_intelligence"])

    def test_a_stored_admin_sections_grant_fails_with_the_reason(self):
        action = self.stored_action(
            self.staffer, self.staffer, {"admin_apps": ["authn", "system_intelligence", "core"]}
        )

        with self.assertRaises(actions.ActionRefused):
            actions.approve_action_request(action.pk, self.staffer)

        self.assert_failed_with(action, SECTIONS_REFUSED)
        self.staffer.refresh_from_db()
        self.assertEqual(self.staffer.admin_apps, ["authn", "system_intelligence"])

    def test_a_stored_member_create_with_admin_sections_fails_with_the_reason(self):
        # Checked before the create runs: without the check, the apply's own validation would fail it for another
        # reason (a new member needs a password, which is never writable).
        action = self.stored(
            self.staffer,
            Action.ACTION_DB_CREATE,
            None,
            {"fields": {"first_name": "New", "admin_apps": ["core"]}},
            model=Member,
        )

        with self.assertRaises(actions.ActionRefused):
            actions.approve_action_request(action.pk, self.staffer)

        self.assert_failed_with(action, SECTIONS_REFUSED)
        self.assertFalse(Member.objects.filter(first_name="New").exists())

    def test_past_the_guard_a_member_create_still_needs_a_password(self):
        # The guard lets the I2G Master's create through; a new member then needs a password, which is never
        # writable, so no one creates members through the assistant.
        action = self.stored(
            self.master, Action.ACTION_DB_CREATE, None, {"fields": {"first_name": "New"}}, model=Member
        )

        with self.assertRaises(ValidationError) as error:
            actions.approve_action_request(action.pk, self.master)

        self.assertIn("password", error.exception.message_dict)
        action.refresh_from_db()
        self.assertEqual(action.status, Action.STATUS_FAILED)
        self.assertFalse(Member.objects.filter(first_name="New").exists())

    def test_a_stored_delete_of_a_privileged_account_fails_with_the_reason(self):
        other_staff = make_admin(apps=["event"], email="other-staff@example.com")
        for target in (self.master, other_staff):
            with self.subTest(target=target.first_name):
                action = self.stored(self.staffer, Action.ACTION_DB_DELETE, target, {})

                with self.assertRaises(actions.ActionRefused):
                    actions.approve_action_request(action.pk, self.staffer)

                self.assert_failed_with(action, TARGET_REFUSED)
                self.assertTrue(Member.objects.filter(pk=target.pk).exists())

    def test_a_non_superuser_cannot_change_or_delete_another_privileged_account(self):
        other_staff = make_admin(apps=["event"], email="other-staff@example.com")
        with acting_as(self.staffer):
            for target in (self.master, other_staff):
                with self.subTest(target=target.first_name):
                    with self.assertRaises(actions.ActionRefused):
                        actions.propose_db_update("authn", "Member", str(target.pk), {"first_name": "Renamed"})
                    with self.assertRaises(actions.ActionRefused):
                        actions.propose_db_delete("authn", "Member", str(target.pk))
        action = self.stored_action(self.staffer, self.master, {"is_active": False})

        with self.assertRaises(actions.ActionRefused):
            actions.approve_action_request(action.pk, self.staffer)

        self.assert_failed_with(action, TARGET_REFUSED)
        self.master.refresh_from_db()
        self.assertTrue(self.master.is_active)

    def test_member_updates_still_work_where_the_admin_allows_them(self):
        with acting_as(self.staffer):
            regular = actions.propose_db_update("authn", "Member", str(self.member.pk), {"title": "Mentor"})
            own = actions.propose_db_update("authn", "Member", str(self.staffer.pk), {"title": "Coordinator"})
        actions.approve_action_request(regular["action_request"]["id"], self.staffer)
        actions.approve_action_request(own["action_request"]["id"], self.staffer)
        with acting_as(self.master):
            grant = actions.propose_db_update("authn", "Member", str(self.staffer.pk), {"admin_apps": ["authn", "cms"]})
        actions.approve_action_request(grant["action_request"]["id"], self.master)

        self.member.refresh_from_db()
        self.staffer.refresh_from_db()
        self.assertEqual((self.member.title, self.staffer.title), ("Mentor", "Coordinator"))
        self.assertEqual(self.staffer.admin_apps, ["authn", "cms"])


class RefusedApprovalViewTests(AuthnWriteGuardTestCase):
    """The chat panel's Approve: a refused change answers with the rule and leaves the request failed, not pending
    behind "Action request not found."."""

    def approve(self, action):
        self.client.force_login(self.staffer)
        return self.client.post(reverse("admin:system_intelligence_action_approve", args=[action.pk]))

    def test_a_refused_approval_names_the_rule_and_fails_the_request(self):
        cases = (
            (self.stored_action(self.staffer, self.master, {"first_name": "Renamed"}), TARGET_REFUSED),
            (self.stored_action(self.staffer, self.staffer, {"admin_apps": ["authn", "core"]}), SECTIONS_REFUSED),
        )
        for action, reason in cases:
            with self.subTest(reason=reason):
                response = self.approve(action)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], reason)
                self.assertEqual(response.json()["action_request"]["status"], Action.STATUS_FAILED)
                self.assert_failed_with(action, reason)
        self.master.refresh_from_db()
        self.staffer.refresh_from_db()
        self.assertEqual((self.master.first_name, self.staffer.admin_apps), ("Admin", ["authn", "system_intelligence"]))

    def test_a_refusal_without_a_stored_reason_still_names_no_missing_request(self):
        # Should the failed approval not have stored its reason (the request changed meanwhile), the answer is still
        # a refusal, not "Action request not found.".
        action = self.stored_action(self.staffer, self.master, {"first_name": "Renamed"})
        with patch.object(actions, "approve_action_request", side_effect=actions.ActionRefused(TARGET_REFUSED)):
            response = self.approve(action)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "You may not make this change.")


class MemberUpdateToolTests(TransactionTestCase):
    """propose_member_update (the assistant's tool) still proposes allowed changes and reports a refusal."""

    def test_allowed_changes_are_proposed_and_refusals_reported(self):
        cache.clear()
        master = make_superuser(email="master@example.com")
        staffer = make_admin(apps=["authn", "system_intelligence"], email="staffer@example.com")
        member = make_member(email="member@example.com", first_name="Ada", last_name="Member")
        with acting_as(staffer):
            proposed = asyncio.run(system_intelligence_tools.propose_member_update(str(member.pk), {"title": "Mentor"}))
            refused = asyncio.run(
                system_intelligence_tools.propose_member_update(str(master.pk), {"first_name": "Renamed"})
            )

        self.assertEqual(proposed["action_request"]["status"], Action.STATUS_PENDING)
        self.assertIn("Tool error: Only an I2G Master may change or delete", refused["result"])
        self.assertTrue(Member.objects.filter(pk=master.pk, first_name="Admin").exists())
