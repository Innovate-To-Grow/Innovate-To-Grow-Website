"""Email Monitoring → Bounced addresses: the confirm → apply POSTs, bulk actions, the counts rebuild, and the
skipped-recipient notice on campaign previews."""

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.event.tests.helpers import make_admin, make_event, make_registration, make_superuser, make_ticket
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, EmailCampaign
from apps.mail.services.email_monitoring.addresses.guards import fingerprint, load_target
from apps.mail.tests.services.bounced_addresses.helpers import add_email, make_bounce, make_person, make_row, settled

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


class BulkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_admin(apps=["mail"], email="mailstaff@example.org"))
        make_person("member@example.org")
        self.member_row = make_row("member@example.org")
        self.list_row = make_row("list@example.org")
        self.done_row = make_row("done@example.org", status=Status.DISMISSED)

    def test_review_lists_what_changes_and_what_is_skipped(self):
        response = self.client.post(
            reverse(BULK), {"action": "suppress", "ids": [self.member_row.pk, self.list_row.pk]}
        )

        outcomes = {entry["row"].address: entry["verdict"] for entry in response.context["entries"]}
        self.assertTrue(outcomes["list@example.org"].allowed)
        self.assertIn("use Mark undeliverable", outcomes["member@example.org"].reason)
        self.assertEqual(response.context["allowed"], 1)
        self.list_row.refresh_from_db()
        self.assertIsNone(self.list_row.suppressed_at)

    def test_apply_changes_the_rows_that_pass_and_reports_the_others(self):
        review = self.client.post(
            reverse(BULK), {"action": "dismiss", "ids": [self.member_row.pk, self.list_row.pk, self.done_row.pk]}
        )
        posted = {"action": "dismiss", "step": "apply", "note": "Old blast", "ids": []}
        for entry in review.context["entries"]:
            posted["ids"].append(entry["row"].pk)
            posted[f"fp_{entry['row'].pk}"] = entry["fingerprint"]
        BouncedAddress.objects.filter(pk=self.list_row.pk).update(suppressed_at=timezone.now())  # changes meanwhile

        response = self.client.post(reverse(BULK), posted)

        self.assertEqual([row.address for row in response.context["applied"]], ["member@example.org"])
        skipped = {row.address: reason for row, reason in response.context["skipped"]}
        self.assertIn("changed since", skipped["list@example.org"])
        self.assertIn("Only an open address", skipped["done@example.org"])
        self.member_row.refresh_from_db()
        self.assertEqual((self.member_row.status, self.member_row.review_note), (Status.DISMISSED, "Old blast"))

    def test_account_and_contact_changes_are_never_offered_in_bulk(self):
        for action in ("delete_account", "deactivate", "delete_email", "replace", "make_primary", ""):
            with self.subTest(action=action):
                response = self.client.post(reverse(BULK), {"action": action, "ids": [self.member_row.pk]})
                self.assertRedirects(response, reverse(LIST), fetch_redirect_response=False)

    def test_an_empty_selection_goes_back_to_the_list(self):
        response = self.client.post(reverse(BULK), {"action": "dismiss", "ids": ["not-a-uuid"]})

        self.assertRedirects(response, reverse(LIST), fetch_redirect_response=False)
        self.assertIn("Select at least one address.", messages_of(response))


class RebuildTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_rebuild_is_confirmed_then_recounts_and_is_audited(self):
        make_bounce(recipient="r@example.org")
        make_row("r@example.org", hard_count=7, status=Status.DISMISSED)

        confirm = self.client.post(reverse(REBUILD))
        self.assertContains(confirm, "Reports already purged cannot be counted again")
        self.assertEqual(BouncedAddress.objects.get(address="r@example.org").hard_count, 7)

        with settled():
            response = self.client.post(reverse(REBUILD), {"step": "apply"})

        self.assertRedirects(response, reverse(LIST), fetch_redirect_response=False)
        row = BouncedAddress.objects.get(address="r@example.org")
        self.assertEqual((row.hard_count, row.status), (1, Status.DISMISSED))
        audit = BouncedAddressAction.objects.get(action="rebuild")
        # The stored report had no reason: classifying it again with the current rules gave it one.
        self.assertEqual(audit.details, {"counted": 1, "reclassified": 1})
        state = BounceAggregationState.objects.get(source="graph")
        entry = LogEntry.objects.get(object_id=str(state.pk))
        self.assertIn("Bounced addresses: rebuilt the counts from the stored records (1 counted)", entry.change_message)

    def test_only_an_i2g_master_may_rebuild(self):
        make_row("kept@example.org", hard_count=7)
        self.client.force_login(make_admin(apps=["mail", "authn"], email="mailstaff@example.org"))

        listing = self.client.get(reverse(LIST))
        for data in ({}, {"step": "apply"}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(reverse(REBUILD), data).status_code, 403)

        self.assertNotContains(listing, reverse(REBUILD))
        self.assertEqual(BouncedAddress.objects.get(address="kept@example.org").hard_count, 7)
        self.assertFalse(BouncedAddressAction.objects.filter(action="rebuild").exists())


class CampaignPreviewNoticeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        make_person("kept@example.org")
        make_person("blocked@example.org")
        make_row("blocked@example.org", suppressed_at=timezone.now(), suppression="undeliverable")
        self.campaign = EmailCampaign.objects.create(
            name="Fall news",
            subject="News",
            body="<p>x</p>",
            audience_type="manual",
            manual_emails="kept@example.org\nblocked@example.org",
            status="draft",
        )

    def test_the_previews_and_the_confirmation_say_how_many_were_skipped(self):
        for name in ("preview_recipients", "send_preview", "send_confirm"):
            with self.subTest(page=name):
                response = self.client.get(reverse(f"admin:mail_emailcampaign_{name}", args=[self.campaign.pk]))
                self.assertContains(response, "1 recipient skipped: undeliverable")
        preview = self.client.get(reverse("admin:mail_emailcampaign_preview_recipients", args=[self.campaign.pk]))
        self.assertEqual([row["email"] for row in preview.context["recipients"]], ["kept@example.org"])
        self.assertContains(preview, "Skipped recipients (1)")
