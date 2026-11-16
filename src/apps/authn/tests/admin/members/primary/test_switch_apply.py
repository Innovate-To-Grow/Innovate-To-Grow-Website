from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.db import DatabaseError
from django.test import override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.authn.tests.admin.members.primary.test_switch_page import texts

from .fixtures import SwitchFixture, change_url, history, switch_url, types


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SwitchApplyTests(SwitchFixture):
    def test_confirming_switches_records_and_returns_to_the_member(self):
        response = self.apply(self.jane, self.secondary)

        self.assertRedirects(response, change_url(self.jane), fetch_redirect_response=False)
        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
        self.assertEqual(types(self.jane)["jane@example.com"], "secondary")
        self.assertEqual(types(self.jane)["jane.old@example.com"], "other")
        summary = (
            "Primary email switched from jane@example.com to jane.work@example.com: jane@example.com is now the "
            "secondary. (Switch primary email on the member page)"
        )
        self.assertEqual(history(self.jane), [summary])
        self.assertEqual(history(self.primary), [f"Email type changed from primary to secondary. {summary}"])
        self.assertEqual(history(self.secondary), [f"Email type changed from secondary to primary. {summary}"])
        self.assertEqual(history(self.unverified), [])
        self.assertIn(
            "jane.work@example.com is now the primary email of Jane Doe. jane@example.com is now the secondary. No "
            "subscription or verification changed, and nothing was sent.",
            texts(response),
        )

    def test_the_history_shows_on_the_member_page(self):
        self.apply(self.jane, self.secondary)

        response = self.client.get(reverse("admin:authn_member_history", args=[self.jane.pk]))

        self.assertContains(response, "Primary email switched from jane@example.com to jane.work@example.com")

    def test_switching_to_an_unsubscribed_address_warns_after_the_switch(self):
        ContactEmail.objects.filter(pk=self.secondary.pk).update(subscribe=False)

        response = self.apply(self.jane, self.secondary)

        self.assertIn(
            "jane.work@example.com is unsubscribed, so campaigns to All subscribers sent to the primary email only no "
            "longer reach this member.",
            texts(response),
        )
        self.assertFalse(ContactEmail.objects.get(pk=self.secondary.pk).subscribe)

    def test_switching_between_two_unsubscribed_addresses_announces_no_loss(self):
        ContactEmail.objects.filter(pk__in=[self.primary.pk, self.secondary.pk]).update(subscribe=False)

        response = self.apply(self.jane, self.secondary)

        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
        # They got no "primary email only" newsletters before the switch either.
        self.assertFalse(any("no longer reach" in text for text in texts(response)), texts(response))

    def test_the_history_is_written_in_the_switchs_transaction(self):
        fingerprint = self.client.get(switch_url(self.jane, self.secondary)).context["fingerprint"]

        with patch.object(LogEntry.objects, "log_actions", side_effect=DatabaseError("history unavailable")):
            with self.assertRaises(DatabaseError):
                self.apply(self.jane, self.secondary, fingerprint=fingerprint)

        # A switch is never committed without its History.
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")
        self.assertEqual(types(self.jane)["jane.work@example.com"], "secondary")

    def test_a_stale_page_changes_nothing_and_is_shown_again(self):
        fingerprint = self.client.get(switch_url(self.jane, self.secondary)).context["fingerprint"]
        ContactEmail.objects.filter(pk=self.primary.pk).update(subscribe=False)  # someone else, meanwhile

        response = self.apply(self.jane, self.secondary, fingerprint=fingerprint)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")
        self.assertTrue(any("changed after the page was shown" in text for text in texts(response)))
        self.assertEqual(response.context["target"], self.secondary)
        self.assertNotEqual(response.context["fingerprint"], fingerprint)
        self.assertFalse(LogEntry.objects.exists())

    def test_a_post_without_the_pages_fingerprint_changes_nothing(self):
        response = self.apply(self.jane, self.secondary, fingerprint="")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_a_forged_unverified_target_is_refused_with_what_to_do(self):
        fingerprint = self.client.get(switch_url(self.jane)).context["fingerprint"]

        response = self.apply(self.jane, self.unverified, fingerprint=fingerprint)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(types(self.jane)["jane.old@example.com"], "other")
        self.assertTrue(any("is not verified, so it cannot become the primary" in text for text in texts(response)))
        self.assertFalse(LogEntry.objects.exists())

    def test_another_members_address_is_refused(self):
        fingerprint = self.client.get(switch_url(self.jane)).context["fingerprint"]

        response = self.apply(self.jane, self.staffer_backup, fingerprint=fingerprint)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(types(self.staffer)["sam.home@example.com"], "secondary")
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_the_current_primary_changes_nothing(self):
        fingerprint = self.client.get(switch_url(self.jane)).context["fingerprint"]

        response = self.apply(self.jane, self.primary, fingerprint=fingerprint)

        self.assertIn("jane@example.com is already the primary email. Nothing was changed.", texts(response))
        self.assertFalse(LogEntry.objects.exists())

    def test_a_member_with_no_primary_gets_one(self):
        ContactEmail.objects.filter(pk=self.primary.pk).delete()

        self.apply(self.jane, self.secondary)

        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
        self.assertEqual(
            history(self.jane),
            [
                "Primary email set to jane.work@example.com (the member had none). "
                "(Switch primary email on the member page)"
            ],
        )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class SwitchTypedConfirmationTests(SwitchFixture):
    def test_the_word_is_asked_for_and_checked(self):
        page = self.client.get(switch_url(self.jane, self.secondary))
        self.assertContains(page, "Type <strong>switch</strong> to confirm:", html=False)

        wrong = self.apply(self.jane, self.secondary, confirm="yes")
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("Type “switch” to confirm. Nothing was changed.", texts(wrong))
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

        right = self.apply(self.jane, self.secondary, confirm=" Switch ")
        self.assertEqual(right.status_code, 302)
        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
