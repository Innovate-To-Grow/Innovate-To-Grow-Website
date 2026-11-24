from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, EmailCampaign
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member
from apps.mail.tests.admin.email_monitoring.addresses.test_addresses_actions_admin import (
    BULK,
    LIST,
    REBUILD,
    Status,
    messages_of,
)
from apps.mail.tests.services.bounced_addresses.helpers import make_bounce, make_person, make_row, settled


class BulkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_admin(email="admin-bulk@example.org"))
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

    def test_every_admin_may_rebuild_and_a_member_may_not(self):
        make_row("kept@example.org", hard_count=7)
        self.client.force_login(make_admin(email="any-admin@example.org"))

        self.assertContains(self.client.get(reverse(LIST)), reverse(REBUILD))
        self.assertContains(self.client.post(reverse(REBUILD)), "Reports already purged cannot be counted again")
        assert_refused_to_member(self, reverse(REBUILD), make_member(), "post", data={"step": "apply"})

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
