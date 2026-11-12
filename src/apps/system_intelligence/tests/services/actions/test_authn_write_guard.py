"""The assistant's record writes can't move sign-in factors or cross the staff/superuser line.

An approved DB action used to run ``full_clean()`` and ``save()`` with only the section grant checked. A staffer with the
Members (authn) and System Intelligence grants, approving their own proposals, could keep a moved phone verified,
verify a phone without a code, move a verified phone onto the I2G Master's account, forge a verified phone challenge,
and give themselves more admin sections (``admin_apps``). Now contact rows and verification challenges are read-only
to the assistant, and member writes follow ``MemberAdmin``'s rules (``member_guard``). Proposals are refused at once,
and an action stored before this check is refused at approval.
"""

import asyncio
import json
from contextlib import contextmanager
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.authn.models import AdminInvitation, ContactEmail, ContactPhone, Member, PhoneVerificationChallenge
from apps.event.tests.helpers import make_admin, make_member, make_superuser
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services import tools as system_intelligence_tools
from apps.system_intelligence.services.actions.orm import serialize_model_instance

Action = SystemIntelligenceActionRequest
WRITE_REFUSED = "Write access is not allowed for authn.{}."


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
        conversation = ChatConversation.objects.create(created_by=user)
        return Action.objects.create(
            conversation=conversation,
            created_by=user,
            action_type=Action.ACTION_DB_UPDATE,
            target_app_label=obj._meta.app_label,
            target_model=obj._meta.object_name,
            target_pk=str(obj.pk),
            payload={"changes": changes},
            before_snapshot=serialize_model_instance(obj, write=True),
        )


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


class MemberWriteTests(AuthnWriteGuardTestCase):
    def test_a_non_superuser_cannot_grant_admin_sections(self):
        for target in (self.staffer, self.member):
            with self.subTest(target=target.first_name), acting_as(self.staffer):
                with self.assertRaises(PermissionDenied) as error:
                    actions.propose_db_update("authn", "Member", str(target.pk), {"admin_apps": ["core", "cms"]})
                self.assertEqual(str(error.exception), "Only an I2G Master may change admin_apps.")
        with acting_as(self.staffer), self.assertRaises(PermissionDenied):
            actions.propose_db_create("authn", "Member", {"first_name": "New", "admin_apps": ["core"]})

        self.staffer.refresh_from_db()
        self.assertEqual(self.staffer.admin_apps, ["authn", "system_intelligence"])

    def test_a_stored_admin_sections_grant_is_refused_and_stays_pending(self):
        action = self.stored_action(
            self.staffer, self.staffer, {"admin_apps": ["authn", "system_intelligence", "core"]}
        )

        with self.assertRaises(PermissionDenied):
            actions.approve_action_request(action.pk, self.staffer)

        action.refresh_from_db()
        self.staffer.refresh_from_db()
        self.assertEqual(action.status, Action.STATUS_PENDING)
        self.assertEqual(self.staffer.admin_apps, ["authn", "system_intelligence"])

    def test_a_non_superuser_cannot_change_or_delete_another_privileged_account(self):
        other_staff = make_admin(apps=["event"], email="other-staff@example.com")
        with acting_as(self.staffer):
            for target in (self.master, other_staff):
                with self.subTest(target=target.first_name):
                    with self.assertRaises(PermissionDenied):
                        actions.propose_db_update("authn", "Member", str(target.pk), {"first_name": "Renamed"})
                    with self.assertRaises(PermissionDenied):
                        actions.propose_db_delete("authn", "Member", str(target.pk))
        action = self.stored_action(self.staffer, self.master, {"is_active": False})

        with self.assertRaises(PermissionDenied):
            actions.approve_action_request(action.pk, self.staffer)

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
