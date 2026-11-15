"""Members → a member → Switch primary email: the page changes nothing, the POST switches, both are guarded."""

import uuid
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.db import DatabaseError
from django.test import Client, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail

from .fixtures import SwitchFixture, add_email, change_url, history, switch_url, types


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SwitchPageTests(SwitchFixture):
    def test_the_page_shows_what_changes_and_changes_nothing(self):
        response = self.client.get(switch_url(self.jane, self.secondary))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/authn/member/switch_primary.html")
        self.assertContains(
            response,
            "Make <strong>jane.work@example.com</strong> the primary email instead of "
            "<strong>jane@example.com</strong>?",
            html=False,
        )
        rows = {row["email"].email_address: (row["type"], row["after"]) for row in response.context["rows"]}
        self.assertEqual(
            rows,
            {
                "jane@example.com": ("Primary", "Secondary"),
                "jane.work@example.com": ("Secondary", "Primary"),
                "jane.old@example.com": ("Other", ""),
            },
        )
        self.assertContains(response, 'name="fingerprint"')
        self.assertContains(response, f'name="to" value="{self.secondary.pk}"')
        self.assertNotContains(response, 'name="confirm"')  # no typed word while confirmations are off
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")
        self.assertFalse(LogEntry.objects.exists())

    def test_with_one_candidate_the_page_goes_straight_to_it(self):
        response = self.client.get(switch_url(self.jane))

        self.assertEqual(response.context["target"], self.secondary)

    def test_with_several_candidates_the_page_asks_which(self):
        third = add_email(self.jane, "jane.home@example.com", "other", days_ago=5)

        response = self.client.get(switch_url(self.jane))

        self.assertIsNone(response.context["target"])
        self.assertContains(response, "Choose the verified address that becomes the primary email.")
        self.assertContains(response, f"{switch_url(self.jane)}?to={self.secondary.pk}")
        self.assertContains(response, f"{switch_url(self.jane)}?to={third.pk}")
        reasons = {row["email"].email_address: row["reason"] for row in response.context["rows"]}
        self.assertEqual(reasons["jane@example.com"], "Current primary")
        self.assertEqual(reasons["jane.old@example.com"], "Verify first")
        # Picking one leads to its confirmation, which offers to go back to the choice.
        response = self.client.get(switch_url(self.jane, third))
        self.assertContains(response, "Choose another address")

    def test_an_address_that_cannot_become_primary_is_explained(self):
        cases = {
            self.unverified.pk: "jane.old@example.com is not verified, so it cannot become the primary",
            self.primary.pk: "jane@example.com is already the primary email.",
            uuid.uuid4(): "That address is not this member's.",
        }
        for target, message in cases.items():
            with self.subTest(message=message):
                response = self.client.get(f"{switch_url(self.jane)}?to={target}")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(any(message in text for text in texts(response)), texts(response))
                self.assertIsNone(response.context["target"])

    def test_no_other_verified_address_explains_how_to_add_one(self):
        ContactEmail.objects.filter(pk=self.secondary.pk).update(verified=False)

        response = self.client.get(switch_url(self.jane))

        self.assertContains(response, "This member has no other verified email address")
        self.assertContains(response, 'id="switch-how-to"')
        self.assertNotContains(response, 'name="fingerprint"')

    def test_a_member_with_no_email_at_all(self):
        response = self.client.get(switch_url(self.outsider))

        self.assertContains(response, "This member has no email address.")

    def test_an_unknown_member_is_a_404(self):
        response = self.client.get(f"/admin/authn/member/{uuid.uuid4()}/switch-primary/")

        self.assertEqual(response.status_code, 404)


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


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SwitchPermissionTests(SwitchFixture):
    def test_staff_without_the_members_app_cannot_open_it(self):
        self.client.force_login(self.outsider)

        self.assertEqual(self.client.get(switch_url(self.jane)).status_code, 403)
        self.assertEqual(self.apply(self.jane, self.secondary, fingerprint="x").status_code, 403)
        # Same answer for a member that does not exist, so the page does not tell which ids do.
        self.assertEqual(self.client.get(f"/admin/authn/member/{uuid.uuid4()}/switch-primary/").status_code, 403)

    def test_the_post_needs_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.master)
        fingerprint = client.get(switch_url(self.jane, self.secondary)).context["fingerprint"]

        response = client.post(switch_url(self.jane), {"to": str(self.secondary.pk), "fingerprint": fingerprint})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_a_helper_may_switch_a_regular_member(self):
        self.client.force_login(self.helper)

        response = self.apply(self.jane, self.secondary)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
        self.assertEqual(LogEntry.objects.filter(user=self.helper).count(), 3)

    def test_only_the_i2g_master_may_switch_another_staff_account(self):
        self.client.force_login(self.helper)

        page = self.client.get(switch_url(self.staffer))
        post = self.client.post(
            switch_url(self.staffer), {"to": str(self.staffer_backup.pk), "fingerprint": "x", "confirm": ""}
        )

        self.assertEqual(page.status_code, 403)
        self.assertEqual(post.status_code, 403)
        self.assertEqual(types(self.staffer)["sam@example.com"], "primary")

    def test_the_i2g_master_may_switch_a_staff_account(self):
        response = self.apply(self.staffer, self.staffer_backup)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(types(self.staffer)["sam.home@example.com"], "primary")

    def test_a_helper_may_switch_their_own_account_and_is_told_where_codes_go(self):
        self.client.force_login(self.helper)

        page = self.client.get(switch_url(self.helper, self.helper_backup))
        self.assertContains(page, "This is your own account: your next admin sign-in code goes to hal.home@example.com")

        self.assertEqual(self.apply(self.helper, self.helper_backup).status_code, 302)
        self.assertEqual(types(self.helper)["hal.home@example.com"], "primary")

    def test_signed_out_visitors_are_sent_to_the_admin_login(self):
        self.client.logout()

        response = self.client.get(switch_url(self.jane))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
