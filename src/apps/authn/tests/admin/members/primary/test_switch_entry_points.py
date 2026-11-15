"""Where the switch starts (the member page's button and row links, the Contact Emails action) and what the page
says about signing in and newsletters."""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.db import DatabaseError, connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.authn.models import ContactEmail

from .fixtures import SwitchFixture, add_email, change_url, history, switch_url, types

EMAILS = reverse("admin:authn_contactemail_changelist")


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MemberPageEntryPointTests(SwitchFixture):
    def test_the_member_page_offers_the_button_and_a_link_on_each_verified_row(self):
        response = self.client.get(change_url(self.jane))

        # The "Switch primary email" button at the top (the row links carry ``?to=``).
        self.assertContains(response, f'href="{switch_url(self.jane)}"')
        self.assertContains(response, f"{switch_url(self.jane)}?to={self.secondary.pk}")
        self.assertContains(response, "Make primary…")
        self.assertContains(response, "Current primary")
        self.assertContains(response, "Verify first")
        self.assertNotContains(response, f"?to={self.unverified.pk}")

    def test_a_helper_sees_neither_on_another_staff_account(self):
        self.client.force_login(self.helper)

        response = self.client.get(change_url(self.staffer))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, switch_url(self.staffer))
        self.assertNotContains(response, "Make primary…")

    def test_a_helper_sees_both_on_a_regular_member(self):
        self.client.force_login(self.helper)

        response = self.client.get(change_url(self.jane))

        self.assertContains(response, f'href="{switch_url(self.jane)}"')
        self.assertContains(response, f"{switch_url(self.jane)}?to={self.secondary.pk}")

    def test_the_inline_errors_point_at_the_new_button(self):
        from apps.authn.admin.members import inlines

        for message in (
            inlines.PRIMARY_EMAIL_INLINE_EDIT_ERROR,
            inlines.PRIMARY_EMAIL_INLINE_DELETE_ERROR,
            inlines.PRIMARY_EMAIL_INLINE_PROMOTION_ERROR,
        ):
            with self.subTest(message=message):
                self.assertIn("Switch primary email", message)
                self.assertNotIn("Contact Emails admin", message)

    def test_the_add_page_has_no_switch(self):
        response = self.client.get(reverse("admin:authn_member_add"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "switch-primary")

    def test_deciding_on_the_button_does_not_load_the_whole_member_again(self):
        model_admin = self.client.get(change_url(self.jane)).context["adminform"].model_admin
        request = RequestFactory().get(change_url(self.jane))
        request.user = self.master

        with CaptureQueriesContext(connection) as queries:
            actions = model_admin.get_actions_detail(request, str(self.jane.pk))

        self.assertEqual([item.action_name for item in actions], ["authn_member_switch_primary_email"])
        # One small query: no profile image, no prefetched contacts.
        self.assertEqual(len(queries), 1, [query["sql"] for query in queries])
        self.assertNotIn("profile_image", queries[0]["sql"])
        self.assertEqual(model_admin.get_actions_detail(request, "not-a-member-id"), [])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SwitchNotesTests(SwitchFixture):
    def notes(self, member, target):
        return self.client.get(switch_url(member, target)).context["notes"]

    def test_a_regular_member(self):
        notes = self.notes(self.jane, self.secondary)

        self.assertIn("both jane@example.com and jane.work@example.com keep working", notes["sign_in"][0])
        self.assertFalse(any("Admin sign-in codes" in note for note in notes["sign_in"]))
        self.assertTrue(any("password" in note and "jane.work@example.com" in note for note in notes["sign_in"]))
        # A forgotten-password code goes to the verified address the member types, so the old primary still gets one.
        self.assertTrue(
            any(
                "forgotten-password code" in note and "(jane@example.com included)" in note for note in notes["sign_in"]
            )
        )
        # Switching to the secondary moves nothing aside, so switching back restores every type.
        self.assertFalse(any("does not move" in note for note in notes["unchanged"]))
        self.assertEqual(
            notes["newsletters"][0]["text"],
            "Campaigns to All subscribers sent to the primary email only go to jane.work@example.com from now on.",
        )
        self.assertTrue(any("Event registrations keep the address" in note for note in notes["unchanged"]))
        self.assertTrue(
            any("To undo, switch back: jane@example.com stays verified" in note for note in notes["unchanged"])
        )
        self.assertIn("Bounced addresses", notes["bounce"])

    def test_a_staff_account_moves_admin_sign_in(self):
        notes = self.notes(self.staffer, self.staffer_backup)

        self.assertIn(
            "Admin sign-in codes go only to a staff member's verified primary: from now on to sam.home@example.com, and "
            "sam@example.com no longer receives them.",
            notes["sign_in"],
        )
        self.assertFalse(any("your own account" in note for note in notes["sign_in"]))

    def test_an_unsubscribed_new_primary_is_a_warning(self):
        ContactEmail.objects.filter(pk=self.secondary.pk).update(subscribe=False)

        first = self.notes(self.jane, self.secondary)["newsletters"][0]

        self.assertEqual(first["level"], "warning")
        self.assertIn("jane.work@example.com is unsubscribed (jane@example.com is subscribed)", first["text"])
        self.assertIn("The switch changes no subscription", first["text"])

    def test_switching_to_an_other_address_says_what_switching_back_leaves(self):
        home = add_email(self.jane, "jane.home@example.com", "other", days_ago=5)

        unchanged = self.notes(self.jane, home)["unchanged"]

        self.assertTrue(
            any(
                "does not move jane.work@example.com back: it stays other" in note
                and "jane.home@example.com becomes the secondary" in note
                for note in unchanged
            ),
            unchanged,
        )

    def test_an_unsubscribed_new_primary_is_only_a_note_when_nothing_changes(self):
        ContactEmail.objects.filter(pk__in=[self.primary.pk, self.secondary.pk]).update(subscribe=False)

        first = self.notes(self.jane, self.secondary)["newsletters"][0]

        self.assertEqual(first["level"], "info")
        self.assertIn("did not reach this member before the switch and still will not", first["text"])
        self.assertNotIn("no longer", first["text"])

    def test_an_unsubscribed_old_primary_is_a_warning(self):
        ContactEmail.objects.filter(pk=self.primary.pk).update(subscribe=False)

        first = self.notes(self.jane, self.secondary)["newsletters"][0]

        self.assertEqual(first["level"], "warning")
        self.assertIn("jane@example.com is unsubscribed but jane.work@example.com is subscribed", first["text"])

    def test_the_page_renders_the_warnings(self):
        ContactEmail.objects.filter(pk=self.secondary.pk).update(subscribe=False)

        response = self.client.get(switch_url(self.jane, self.secondary))

        self.assertContains(response, "jane.work@example.com is unsubscribed")
        self.assertContains(response, 'id="switch-sign-in"')
        self.assertContains(response, 'id="switch-unchanged"')

    def test_an_unverified_old_primary(self):
        ContactEmail.objects.filter(pk=self.primary.pk).update(verified=False)

        notes = self.notes(self.jane, self.secondary)

        self.assertIn("jane@example.com (not verified) still does not", notes["sign_in"][0])
        self.assertIn(
            "jane@example.com is not verified, so it cannot be made the primary again until it is verified.",
            notes["unchanged"],
        )

    def test_no_old_primary(self):
        ContactEmail.objects.filter(pk=self.primary.pk).delete()

        notes = self.notes(self.jane, self.secondary)

        self.assertIn("jane.work@example.com keeps working.", notes["sign_in"][0])
        self.assertEqual(notes["bounce"], "")
        self.assertEqual(len(notes["unchanged"]), 1)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ContactEmailsActionTests(SwitchFixture):
    def run_action(self, contact):
        data = {"action": "make_primary", "_selected_action": [str(contact.pk)], "select_across": "0", "index": "0"}
        return self.client.post(EMAILS, data, follow=True)

    def test_the_action_switches_and_now_records_history(self):
        response = self.run_action(self.secondary)

        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")
        summary = (
            "Primary email switched from jane@example.com to jane.work@example.com: jane@example.com is now the "
            "secondary. (Make selected email primary in Contact Emails)"
        )
        self.assertEqual(history(self.jane), [summary])
        self.assertEqual(history(self.secondary), [f"Email type changed from secondary to primary. {summary}"])
        self.assertEqual(history(self.primary), [f"Email type changed from primary to secondary. {summary}"])
        self.assertIn(
            "jane.work@example.com is now the primary email of Jane Doe. jane@example.com is now the secondary. No "
            "subscription or verification changed, and nothing was sent.",
            texts(response),
        )

    def test_the_history_is_written_in_the_switchs_transaction(self):
        with patch.object(LogEntry.objects, "log_actions", side_effect=DatabaseError("history unavailable")):
            with self.assertRaises(DatabaseError):
                self.run_action(self.secondary)

        # A switch is never committed without its History.
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")
        self.assertEqual(types(self.jane)["jane.work@example.com"], "secondary")

    def test_an_unverified_address_is_refused_with_what_to_do(self):
        response = self.run_action(self.unverified)

        self.assertEqual(types(self.jane)["jane.old@example.com"], "other")
        self.assertTrue(any("jane.old@example.com is not verified" in text for text in texts(response)))
        self.assertFalse(LogEntry.objects.exists())

    def test_the_owner_guard_still_applies(self):
        self.client.force_login(self.helper)

        response = self.run_action(self.staffer_backup)

        self.assertEqual(types(self.staffer)["sam@example.com"], "primary")
        self.assertTrue(any("only an I2G Master may change those" in text for text in texts(response)))
        self.assertFalse(LogEntry.objects.exists())

    def test_the_list_shows_the_account_flag_next_to_the_address_flags(self):
        add_email(None, "nobody@example.com", "other")

        response = self.client.get(EMAILS)

        self.assertContains(response, "Account active")
        rows = {row.email_address: row for row in response.context["cl"].result_list}
        admin_obj = response.context["cl"].model_admin
        self.assertTrue(admin_obj.account_active(rows["jane@example.com"]))
        self.assertIsNone(admin_obj.account_active(rows["nobody@example.com"]))
