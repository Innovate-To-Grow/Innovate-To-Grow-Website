import uuid
from unittest.mock import patch

from django.core import signing
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.unsubscribe import (
    _RESUBSCRIBE_SALT,
    build_resubscribe_token,
    load_resubscribe_token,
)


class PerAddressResubscribeTests(APITestCase):
    """Tokens carrying ``email_ids`` restore exactly those addresses; older tokens fall back to the primary."""

    def setUp(self):
        cache.clear()
        task_patcher = patch(
            "apps.mail.services.tokens.notifications.start_in_process_task",
            side_effect=lambda target, *args, **_kwargs: target(*args),
        )
        task_patcher.start()
        self.addCleanup(task_patcher.stop)
        self.member = make_member(email="per-address@example.com")
        self.primary = ContactEmail.objects.get(member=self.member, email_type="primary")
        self.secondary = ContactEmail.objects.create(
            member=self.member, email_address="per-address-2@example.com", email_type="secondary"
        )
        self.other = ContactEmail.objects.create(
            member=self.member, email_address="per-address-3@example.com", email_type="other"
        )
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)

    def _flags(self, member=None):
        return {row.email_address: row.subscribe for row in ContactEmail.objects.filter(member=member or self.member)}

    def _post(self, token):
        return self.client.post(f"/mail/resubscribe/{token}/")

    def test_restores_exactly_the_token_ids(self):
        token = build_resubscribe_token(self.member, email_ids=[self.secondary.pk, self.other.pk])

        response = self._post(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._flags(),
            {"per-address@example.com": False, "per-address-2@example.com": True, "per-address-3@example.com": True},
        )

    def test_old_format_token_falls_back_to_primary(self):
        token = signing.dumps({"member_id": str(self.member.pk)}, salt="mail-resubscribe", compress=True)

        response = self._post(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._flags(),
            {"per-address@example.com": True, "per-address-2@example.com": False, "per-address-3@example.com": False},
        )

    def test_ids_of_another_member_are_ignored(self):
        stranger = make_member(email="stranger@example.com")
        ContactEmail.objects.filter(member=stranger).update(subscribe=False)
        stranger_email = ContactEmail.objects.get(member=stranger)
        token = build_resubscribe_token(self.member, email_ids=[stranger_email.pk, self.secondary.pk])

        response = self._post(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._flags(stranger), {"stranger@example.com": False})
        self.assertTrue(self._flags()["per-address-2@example.com"])

    def test_deleted_address_is_skipped(self):
        token = build_resubscribe_token(self.member, email_ids=[self.secondary.pk, self.other.pk])
        self.other.delete()

        response = self._post(token)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._flags()["per-address-2@example.com"])

    @patch("apps.authn.services.email.send_notification_email")
    def test_nothing_to_restore_says_so_and_sends_nothing(self, mock_send):
        """Every id gone, or an old-format token for a member without a primary: no false success."""
        no_primary = Member.objects.create_user(password="x", first_name="Np")
        ContactEmail.objects.create(member=no_primary, email_address="np-other@example.com", email_type="other")
        ContactEmail.objects.filter(member=no_primary).update(subscribe=False)
        deleted_ids_token = build_resubscribe_token(self.member, email_ids=[self.other.pk])
        self.other.delete()
        cases = {
            "deleted ids": deleted_ids_token,
            "old format without primary": signing.dumps(
                {"member_id": str(no_primary.pk)}, salt=_RESUBSCRIBE_SALT, compress=True
            ),
        }
        for label, token in cases.items():
            with self.subTest(case=label):
                response = self._post(token)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "No changes made")
                self.assertNotContains(response, "You've been resubscribed")
        mock_send.assert_not_called()
        self.assertEqual(self._flags(no_primary), {"np-other@example.com": False})

    @patch("apps.authn.services.email.send_notification_email")
    def test_confirmation_goes_to_primary_even_when_only_other_addresses_change(self, mock_send):
        token = build_resubscribe_token(self.member, email_ids=[self.secondary.pk])

        self._post(token)

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[1]["recipient"], "per-address@example.com")
        self.assertIn("resubscribed", mock_send.call_args[1]["subject"].lower())


class ResubscribeTokenFormatTests(TestCase):
    def setUp(self):
        self.member = make_member(email="format@example.com")

    def test_builder_omits_the_key_without_ids(self):
        payload = signing.loads(build_resubscribe_token(self.member), salt=_RESUBSCRIBE_SALT)

        self.assertEqual(payload, {"member_id": str(self.member.pk)})
        self.assertEqual(load_resubscribe_token(build_resubscribe_token(self.member)), (self.member, None))

    def test_builder_refuses_an_empty_id_list(self):
        with self.assertRaises(ValueError):
            build_resubscribe_token(self.member, email_ids=[])

    def test_ids_round_trip_as_strings(self):
        email_id = uuid.uuid4()

        member, email_ids = load_resubscribe_token(build_resubscribe_token(self.member, email_ids=[email_id]))

        self.assertEqual(member.pk, self.member.pk)
        self.assertEqual(email_ids, [str(email_id)])

    def test_malformed_ids_are_rejected(self):
        for email_ids in ("not-a-list", ["not-a-uuid"], {"id": "x"}):
            with self.subTest(email_ids=email_ids):
                token = signing.dumps(
                    {"member_id": str(self.member.pk), "email_ids": email_ids}, salt=_RESUBSCRIBE_SALT
                )
                with self.assertRaisesMessage(ValueError, "Invalid or expired resubscribe link."):
                    load_resubscribe_token(token)

    def test_explicit_empty_list_is_not_the_primary_fallback(self):
        token = signing.dumps({"member_id": str(self.member.pk), "email_ids": []}, salt=_RESUBSCRIBE_SALT)

        self.assertEqual(load_resubscribe_token(token), (self.member, []))
