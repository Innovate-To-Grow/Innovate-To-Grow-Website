"""The assistant's record writes can't move sign-in factors or cross the staff/superuser line.

An approved DB action used to run ``full_clean()`` and ``save()`` with only the section grant checked. A staffer with the
Members (authn) and System Intelligence grants, approving their own proposals, could keep a moved phone verified,
verify a phone without a code, move a verified phone onto the I2G Master's account, forge a verified phone challenge,
replace the RSA sign-in key, join a group through its table, and give themselves more admin sections (``admin_apps``).
Now contact rows, verification challenges, invitations and the key are read-only to the assistant, many-to-many tables
aren't writable, and member writes stay on the staff side of the line (``member_guard``, stricter than ``MemberAdmin``).
Proposals are refused at once, and an action stored before these checks fails at approval with the reason.
"""

import asyncio
import json
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import (
    AdminInvitation,
    ContactEmail,
    ContactPhone,
    Member,
    PhoneVerificationChallenge,
    RSAKeypair,
)
from apps.event.tests.helpers import make_admin, make_member, make_superuser
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services import tools as system_intelligence_tools
from apps.system_intelligence.services.actions.orm import serialize_model_instance

Action = SystemIntelligenceActionRequest
WRITE_REFUSED = "Write access is not allowed for authn.{}."
TARGET_REFUSED = "Only an I2G Master may change or delete another staff or superuser account."
SECTIONS_REFUSED = "Only an I2G Master may change admin_apps."


@contextmanager
def acting_as(user):
    conversation = ChatConversation.objects.create(created_by=user)
    tokens = actions.set_action_context(str(conversation.pk), str(user.pk))
    try:
        yield conversation
    finally:
        actions.reset_action_context(tokens)


class AuthnWriteGuardTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.master = make_superuser(email="master@example.com")
        self.staffer = make_admin(apps=["authn", "system_intelligence"], email="staffer@example.com")
        self.member = make_member(email="member@example.com", first_name="Ada", last_name="Member")
        self.phone = ContactPhone.objects.create(
            member=self.member, phone_number="2095550123", region="1-US", verified=True
        )

    def stored_action(self, user, obj, changes):
        """A pending update as an earlier proposal would have stored it (before these checks existed)."""
        return self.stored(user, Action.ACTION_DB_UPDATE, obj, {"changes": changes})

    def stored(self, user, action_type, obj, payload, *, model=None):
        """A pending action of ``action_type`` on ``obj`` (or, for a create, on ``model``), as stored before."""
        model = model or type(obj)
        conversation = ChatConversation.objects.create(created_by=user)
        return Action.objects.create(
            conversation=conversation,
            created_by=user,
            action_type=action_type,
            target_app_label=model._meta.app_label,
            target_model=model._meta.object_name,
            target_pk=str(obj.pk) if obj is not None else "",
            payload=payload,
            before_snapshot=serialize_model_instance(obj, write=True) if obj is not None else {},
        )

    def assert_failed_with(self, action, message):
        action.refresh_from_db()
        self.assertEqual((action.status, action.error_message), (Action.STATUS_FAILED, message))


class ContactAndChallengeWriteTests(AuthnWriteGuardTestCase):
    def test_a_phone_cannot_be_moved_or_verified_through_the_assistant(self):
        unverified = ContactPhone.objects.create(member=self.member, phone_number="2095550124", region="1-US")
        proposals = (
            (str(self.phone.pk), {"member_id": str(self.master.pk)}),  # Onto the I2G Master's account.
            (str(self.phone.pk), {"member_id": str(self.staffer.pk)}),
            (str(unverified.pk), {"verified": True}),  # #732: only a code verifies a number.
        )
        with acting_as(self.staffer):
            for pk, changes in proposals:
                with self.subTest(changes=changes), self.assertRaises(actions.ActionRequestError) as error:
                    actions.propose_db_update("authn", "ContactPhone", pk, changes)
                self.assertEqual(str(error.exception), WRITE_REFUSED.format("ContactPhone"))

        self.phone.refresh_from_db()
        unverified.refresh_from_db()
        self.assertEqual(
            (self.phone.member_id, self.phone.verified, unverified.verified), (self.member.pk, True, False)
        )

    def test_a_contact_email_cannot_be_created_or_moved(self):
        # Both payloads are valid records: before, they applied, giving the staffer a verified sign-in address.
        email = ContactEmail.objects.get(member=self.member)
        with acting_as(self.staffer):
            with self.assertRaises(actions.ActionRequestError) as moved:
                actions.propose_db_update(
                    "authn",
                    "ContactEmail",
                    str(email.pk),
                    {"member_id": str(self.staffer.pk), "email_type": "secondary"},
                )
            with self.assertRaises(actions.ActionRequestError) as created:
                actions.propose_db_create(
                    "authn",
                    "ContactEmail",
                    {
                        "member_id": str(self.staffer.pk),
                        "email_address": "added@example.com",
                        "email_type": "secondary",
                        "verified": True,
                    },
                )

        for error in (moved, created):
            self.assertEqual(str(error.exception), WRITE_REFUSED.format("ContactEmail"))
        email.refresh_from_db()
        self.assertEqual(email.member_id, self.member.pk)
        self.assertFalse(ContactEmail.objects.filter(email_address="added@example.com").exists())

    def test_a_stored_contact_write_is_refused_at_approval(self):
        action = self.stored_action(self.staffer, self.phone, {"member_id": str(self.master.pk)})

        with self.assertRaises(actions.ActionRequestError):
            actions.approve_action_request(action.pk, self.staffer)

        action.refresh_from_db()
        self.phone.refresh_from_db()
        self.assertEqual(action.status, Action.STATUS_FAILED)
        self.assertEqual((self.phone.member_id, self.phone.verified), (self.member.pk, True))

    def test_a_verified_phone_challenge_cannot_be_forged(self):
        # A challenge set to "verified" is a grant that event registration accepts as a verified phone.
        challenge = PhoneVerificationChallenge.objects.create(
            phone_number="+12095550125",
            purpose="event_registration",
            member=self.member,
            context_identifier="event-registration:demo",
            code_hash="unusable",
            status="expired",
            expires_at=timezone.now() - timedelta(days=1),
        )
        with acting_as(self.staffer), self.assertRaises(actions.ActionRequestError) as error:
            actions.propose_db_update(
                "authn",
                "PhoneVerificationChallenge",
                str(challenge.pk),
                {"status": "verified", "expires_at": (timezone.now() + timedelta(minutes=10)).isoformat()},
            )

        self.assertEqual(str(error.exception), WRITE_REFUSED.format("PhoneVerificationChallenge"))
        challenge.refresh_from_db()
        self.assertEqual(challenge.status, "expired")

    def test_an_admin_invitation_cannot_be_created_or_redirected(self):
        # Accepting one makes the member who owns its address staff: the admin lets only the I2G Master write them.
        invitation = AdminInvitation.objects.create(
            email="invitee@example.com",
            token=AdminInvitation.generate_token(),
            invited_by=self.master,
            expires_at=timezone.now() + timedelta(days=3),
        )
        with acting_as(self.staffer):
            with self.assertRaises(actions.ActionRequestError) as redirected:
                actions.propose_db_update(
                    "authn", "AdminInvitation", str(invitation.pk), {"email": "member@example.com"}
                )
            with self.assertRaises(actions.ActionRequestError) as created:
                actions.propose_db_create(
                    "authn",
                    "AdminInvitation",
                    {"email": "member@example.com", "expires_at": (timezone.now() + timedelta(days=3)).isoformat()},
                )

        for error in (redirected, created):
            self.assertEqual(str(error.exception), WRITE_REFUSED.format("AdminInvitation"))
        invitation.refresh_from_db()
        self.assertEqual(invitation.email, "invitee@example.com")
        self.assertEqual(AdminInvitation.objects.count(), 1)

    def test_contact_rows_stay_readable(self):
        with acting_as(self.staffer):
            record = json.loads(actions.get_record("authn", "ContactPhone", str(self.phone.pk)))

        self.assertEqual(record["phone_number"], "2095550123")

    def test_the_schema_offers_no_writable_contact_field(self):
        with acting_as(self.staffer):
            phone = json.loads(actions.get_model_schema("authn", "ContactPhone"))
            member = json.loads(actions.get_model_schema("authn", "Member"))

        self.assertEqual(phone["writable_fields"], [])
        self.assertTrue(phone["readable_fields"])
        self.assertIn("title", [field["name"] for field in member["writable_fields"]])

    def test_the_rsa_sign_in_key_cannot_be_replaced_or_switched_off(self):
        # A written public half no longer matches the stored private key: password sign-in (site and admin) breaks
        # until an I2G Master makes a new key. The admin makes keys read-only once created.
        key = RSAKeypair.objects.create(name="site-signing", is_active=True)
        public_key = key.public_key_pem
        with acting_as(self.staffer):
            for changes in (
                {"public_key_pem": "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----"},
                {"is_active": False},
            ):
                with self.subTest(changes=list(changes)), self.assertRaises(actions.ActionRequestError) as error:
                    actions.propose_db_update("authn", "RSAKeypair", str(key.pk), changes)
                self.assertEqual(str(error.exception), WRITE_REFUSED.format("RSAKeypair"))
            record = json.loads(actions.get_record("authn", "RSAKeypair", str(key.pk)))

        key.refresh_from_db()
        self.assertEqual((key.public_key_pem, key.is_active), (public_key, True))
        self.assertEqual(record["public_key_pem"], public_key)

    def test_group_membership_cannot_be_written_through_its_table(self):
        # Member.groups is never writable; its auto-created table must not be either.
        group = Group.objects.create(name="Editors")
        with acting_as(self.staffer), self.assertRaises(actions.ActionRequestError) as error:
            actions.propose_db_create(
                "authn", "Member_groups", {"member_id": str(self.staffer.pk), "group_id": group.pk}
            )

        self.assertEqual(str(error.exception), WRITE_REFUSED.format("Member_groups"))
        self.assertFalse(self.staffer.groups.exists())


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
