"""Members → a member → Switch primary email: the page changes nothing, the POST switches, both are guarded."""

import uuid

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.test import override_settings

from apps.authn.models import ContactEmail

from .fixtures import SwitchFixture, add_email, switch_url, types


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
