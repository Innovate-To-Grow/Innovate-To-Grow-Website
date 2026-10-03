import uuid
from unittest.mock import patch

from django.core import signing
from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.helpers import bearer_header, stale_bearer_headers
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.unsubscribe import (
    _RESUBSCRIBE_SALT,
    build_resubscribe_token,
    load_resubscribe_token,
)


class ResubscribeViewTests(APITestCase):
    def setUp(self):
        cache.clear()
        task_patcher = patch(
            "apps.mail.services.tokens.notifications.start_in_process_task",
            side_effect=lambda target, *args, **_kwargs: target(*args),
        )
        self.start_task = task_patcher.start()
        self.addCleanup(task_patcher.stop)
        self.member = make_member(email="resub@example.com")
        self.primary_email = ContactEmail.objects.get(member=self.member, email_type="primary")
        self.primary_email.subscribe = False
        self.primary_email.save(update_fields=["subscribe"])
        self.token = build_resubscribe_token(self.member)
        self.url = f"/mail/resubscribe/{self.token}/"

    def _is_subscribed(self):
        self.primary_email.refresh_from_db()
        return self.primary_email.subscribe

    def test_valid_post_resubscribes_member(self):
        self.assertFalse(self._is_subscribed())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, "You've been resubscribed")
        self.assertTrue(self._is_subscribed())

    def test_replay_page_does_not_claim_a_resubscribe(self):
        self.client.post(self.url)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No changes made")
        self.assertNotContains(response, "You've been resubscribed")

    def test_signed_in_browser_without_csrf_token_can_resubscribe(self):
        """The done page's form carries no CSRF token; a session cookie must not 403 it."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)

        response = client.post(self.url, {})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._is_subscribed())

    def test_invalid_token_returns_400(self):
        response = self.client.post("/mail/resubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("text/html", response["Content-Type"])

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    @patch("apps.authn.services.email.send_notification_email")
    def test_sends_confirmation_email(self, mock_send):
        self.client.post(self.url)
        self.start_task.assert_called_once()
        self.assertTrue(self.start_task.call_args.kwargs["best_effort_start"])
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "resub@example.com")
        self.assertIn("resubscribed", call_kwargs["subject"].lower())

    @patch("apps.authn.services.email.send_notification_email")
    def test_already_subscribed_no_error(self, mock_send):
        self.primary_email.subscribe = True
        self.primary_email.save(update_fields=["subscribe"])
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.start_task.assert_not_called()
        mock_send.assert_not_called()

    @patch("apps.authn.services.email.send_notification_email")
    def test_replay_is_idempotent_with_a_single_confirmation(self, mock_send):
        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(self._is_subscribed())
        mock_send.assert_called_once()

    def test_head_and_options_are_not_allowed(self):
        for method in ("head", "options"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        self.assertFalse(self._is_subscribed())

    def test_unusual_accept_header_still_resubscribes(self):
        response = self.client.post(self.url, HTTP_ACCEPT="text/plain")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._is_subscribed())

    def test_body_is_never_read(self):
        response = self.client.post(self.url, "{not json", content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._is_subscribed())

    def test_responses_are_never_cached(self):
        for response in (self.client.post(self.url), self.client.post("/mail/resubscribe/garbage-token/")):
            with self.subTest(status=response.status_code):
                self.assertIn("no-store", response["Cache-Control"])

    def test_inactive_member_is_rejected(self):
        Member.objects.filter(pk=self.member.pk).update(is_active=False)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._is_subscribed())

    def test_stale_bearer_does_not_block_resubscribe(self):
        """The link token is the credential; a dead session's Bearer must not 401 it first.

        Resubscribe tokens are short-lived but not one-time, so the observable effect is the flag flip.
        """
        for index, (label, header) in enumerate(stale_bearer_headers().items()):
            with self.subTest(bearer=label):
                member = make_member(email=f"stale-{index}@example.com")
                primary = ContactEmail.objects.get(member=member, email_type="primary")
                primary.subscribe = False
                primary.save(update_fields=["subscribe"])

                response = self.client.post(
                    f"/mail/resubscribe/{build_resubscribe_token(member)}/", HTTP_AUTHORIZATION=header
                )

                self.assertEqual(response.status_code, 200)
                primary.refresh_from_db()
                self.assertTrue(primary.subscribe)

    def test_bearer_of_another_member_resubscribes_the_token_owner(self):
        other = make_member(email="other@example.com")
        other_primary = ContactEmail.objects.get(member=other, email_type="primary")
        other_primary.subscribe = False
        other_primary.save(update_fields=["subscribe"])

        response = self.client.post(self.url, HTTP_AUTHORIZATION=bearer_header(other))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._is_subscribed())
        other_primary.refresh_from_db()
        self.assertFalse(other_primary.subscribe)


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
