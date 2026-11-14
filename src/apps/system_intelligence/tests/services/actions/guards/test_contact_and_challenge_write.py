import json
from datetime import timedelta

from django.contrib.auth.models import Group
from django.utils import timezone

from apps.authn.models import (
    AdminInvitation,
    ContactEmail,
    ContactPhone,
    PhoneVerificationChallenge,
    RSAKeypair,
)
from apps.system_intelligence.services import actions
from apps.system_intelligence.tests.services.actions.guards.test_authn_write_guard import (
    WRITE_REFUSED,
    Action,
    AuthnWriteGuardTestCase,
    acting_as,
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
