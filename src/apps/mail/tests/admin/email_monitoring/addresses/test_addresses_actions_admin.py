"""Email Monitoring → Bounced addresses: the confirm → apply POSTs, bulk actions, the counts rebuild, and the
skipped-recipient notice on campaign previews."""

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, Member
from apps.event.tests.helpers import make_admin, make_event, make_registration, make_superuser, make_ticket
from apps.mail.models import BouncedAddress
from apps.mail.services.email_monitoring.addresses.actions.targets import fingerprint, load_target
from apps.mail.tests.services.bounced_addresses.helpers import add_email, make_person, make_row

LIST = "admin:mail_email_monitoring_addresses"
BULK = "admin:mail_email_monitoring_addresses_bulk"
REBUILD = "admin:mail_email_monitoring_addresses_rebuild"
DETAIL = "admin:mail_email_monitoring_address"
ACTION = "admin:mail_email_monitoring_address_action"
Status = BouncedAddress.Status


def messages_of(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


class ConfirmApplyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.master = make_superuser()
        self.client.force_login(self.master)

    def seen(self, row) -> str:
        return fingerprint(load_target(BouncedAddress.objects.get(pk=row.pk)))

    def test_confirm_shows_the_effect_and_apply_changes_nothing_else(self):
        make_person("member@example.org")
        row = make_row("member@example.org")
        url = reverse(ACTION, args=[row.pk, "mark_undeliverable"])

        confirm = self.client.post(url, {"step": "confirm"})

        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "Every campaign audience skips this address")
        self.assertContains(confirm, confirm.context["fingerprint"])
        row.refresh_from_db()
        self.assertIsNone(row.suppressed_at)

        applied = self.client.post(
            url, {"step": "apply", "fingerprint": confirm.context["fingerprint"], "note": "5.1.1"}
        )

        self.assertRedirects(applied, reverse(DETAIL, args=[row.pk]), fetch_redirect_response=False)
        row.refresh_from_db()
        self.assertEqual((row.suppression, row.suppressed_reason), ("undeliverable", "5.1.1"))
        self.assertIn("campaigns skip it from now on", messages_of(applied)[0])

    def test_a_change_after_the_confirmation_page_refuses_and_shows_it_again(self):
        member = make_person("stale@example.org")
        row = make_row("stale@example.org")
        seen = self.seen(row)
        Member.objects.filter(pk=member.pk).update(is_active=False)

        response = self.client.post(
            reverse(ACTION, args=[row.pk, "mark_undeliverable"]), {"step": "apply", "fingerprint": seen}
        )

        self.assertEqual(response.status_code, 409)
        self.assertNotEqual(response.context["fingerprint"], seen)
        self.assertIn("changed since the confirmation page was shown", messages_of(response)[0])
        row.refresh_from_db()
        self.assertIsNone(row.suppressed_at)

    def test_a_refused_guard_goes_back_to_the_address_with_the_reason(self):
        make_person("member@example.org")
        row = make_row("member@example.org")
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))

        for step in ("confirm", "apply"):
            with self.subTest(step=step):
                response = self.client.post(
                    reverse(ACTION, args=[row.pk, "mark_undeliverable"]), {"step": step, "fingerprint": self.seen(row)}
                )
                self.assertRedirects(response, reverse(DETAIL, args=[row.pk]), fetch_redirect_response=False)
                self.assertIn("Needs the Members (authn) app", messages_of(response)[-1])
        row.refresh_from_db()
        self.assertIsNone(row.suppressed_at)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_delete_email_asks_for_the_typed_address(self):
        member = make_person("keep@example.org")
        add_email(member, "gone@example.org")
        row = make_row("gone@example.org")
        url = reverse(ACTION, args=[row.pk, "delete_email"])

        confirm = self.client.post(url, {"step": "confirm"})
        self.assertContains(confirm, "Type <strong>gone@example.org</strong> to confirm")
        wrong = self.client.post(
            url, {"step": "apply", "fingerprint": confirm.context["fingerprint"], "confirm": "nope"}
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertTrue(ContactEmail.objects.filter(email_address="gone@example.org").exists())

        self.client.post(
            url, {"step": "apply", "fingerprint": confirm.context["fingerprint"], "confirm": "gone@example.org"}
        )

        self.assertFalse(ContactEmail.objects.filter(email_address="gone@example.org").exists())

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_delete_account_lists_the_cascade_and_recommends_deactivating(self):
        member = make_person("doomed@example.org")
        event = make_event()
        make_registration(member, event, make_ticket(event))
        row = make_row("doomed@example.org")

        response = self.client.post(reverse(ACTION, args=[row.pk, "delete_account"]), {"step": "confirm"})

        self.assertContains(response, "Deleting this account also deletes")
        self.assertContains(response, "Event registrations")
        self.assertContains(response, "Recommended: deactivate instead.")
        self.assertContains(response, reverse(ACTION, args=[row.pk, "deactivate"]))
        self.assertContains(response, "Type <strong>doomed@example.org</strong> to confirm")
        self.assertTrue(Member.objects.filter(pk=member.pk).exists())

    def test_replace_offers_only_the_roles_that_apply(self):
        member = make_person("old@example.org")
        add_email(member, "second@example.org", email_type="secondary")
        row = make_row("old@example.org")

        response = self.client.post(reverse(ACTION, args=[row.pk, "replace"]), {"step": "confirm"})

        self.assertTrue(response.context["secondary_taken"])
        self.assertContains(response, 'value="secondary" disabled')
        self.assertContains(response, "Keep it, marked undeliverable (recommended)")

    def test_replace_applies_through_the_page(self):
        member = make_person("old@example.org")
        row = make_row("old@example.org")
        url = reverse(ACTION, args=[row.pk, "replace"])
        confirm = self.client.post(url, {"step": "confirm"})

        response = self.client.post(
            url,
            {
                "step": "apply",
                "fingerprint": confirm.context["fingerprint"],
                "new_address": "new@example.org",
                "new_role": "secondary",
                "old_address": "undeliverable",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ContactEmail.objects.filter(member=member, email_address="new@example.org").exists())
        row.refresh_from_db()
        self.assertEqual(row.suppression, "undeliverable")
