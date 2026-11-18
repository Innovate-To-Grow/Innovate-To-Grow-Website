"""Left-the-organisation notices on the Bounced addresses pages: the counts column and the list's filter, intro and
suggestion; the address page's notice (the address it names, and the link to its helpdesk ticket only for staff with
the Helpdesk app); and the Replace email page's hint, which fills in nothing."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urlencode

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.core.models import InboundMessage
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import BouncedAddress
from apps.mail.tests.services.bounced_addresses.helpers import make_person, make_row

LIST = "admin:mail_email_monitoring_addresses"
DETAIL = "admin:mail_email_monitoring_address"
ACTION = "admin:mail_email_monitoring_address_action"
JORDAN = "jordan.park@contoso.example"
RILEY = "riley.chen@contoso.example"


def notice_row(**values) -> BouncedAddress:
    now = timezone.now()
    source = InboundMessage.objects.create(
        mailbox="i2g@ucmerced.edu",
        graph_id="AAMk-admin-notice",
        received_at=now,
        status=InboundMessage.Status.DONE,
        processed_at=now,
    )
    defaults = {
        "hard_count": 0,
        "graph_first_at": None,
        "graph_last_at": None,
        "last_classification": "",
        "last_category": "",
        "last_status_code": "",
        "last_reason": "",
        "left_org_count": 1,
        "left_org_first_at": now,
        "left_org_last_at": now,
        "left_org_contact": RILEY,
        "left_org_contact_kind": "contact",
        "left_org_contact_name": "Riley Chen",
        "left_org_contact_phone": "+12095550123",
        "left_org_hint_source": source,
        "left_org_hint_expires_at": now + timedelta(days=90),
        "left_org_ticket": 1042,
        "first_bounce_at": now,
        "last_bounce_at": now,
    }
    return make_row(JORDAN, **{**defaults, **values})


class NoticePagesTests(TestCase):
    def setUp(self):
        cache.clear()
        make_person(JORDAN)
        self.row = notice_row()
        self.ticket_link = (
            f"{reverse('admin:helpdesk_ticket_changelist')}?{urlencode({'q': 1042, 'mail': 'all', 'status': 'any'})}"
        )

    def test_the_address_page_shows_the_notice_the_contact_it_names_and_the_ticket(self):
        self.client.force_login(make_superuser())

        response = self.client.get(reverse(DETAIL, args=[self.row.pk]))

        self.assertEqual(self.row.suggestion, BouncedAddress.Suggestion.LEFT_ORG)
        self.assertContains(response, "Left-the-organisation notices")
        self.assertContains(response, f"It names <strong>{RILEY}</strong>: who to contact instead, the notice says.")
        self.assertContains(response, "Contact details need manual review.")
        self.assertContains(response, "Name mentioned: <strong>Riley Chen</strong>.")
        self.assertContains(response, "Phone mentioned: <strong>+12095550123</strong>.")
        self.assertContains(response, "Out-of-office replies are never counted here.")
        self.assertContains(response, self.ticket_link.replace("&", "&amp;"))
        self.assertContains(response, "May have left: an automatic reply says so.")
        self.assertEqual(response.context["notice_link"], self.ticket_link)

    def test_the_ticket_link_needs_the_helpdesk_app(self):
        self.client.force_login(make_admin(apps=["mail"]))

        response = self.client.get(reverse(DETAIL, args=[self.row.pk]))

        self.assertContains(response, "Left-the-organisation notices")
        self.assertNotContains(response, reverse("admin:helpdesk_ticket_changelist"))
        self.assertEqual(response.context["notice_link"], "")

    def test_an_address_without_notices_shows_no_notice_block(self):
        self.client.force_login(make_superuser())
        other = make_row("hard@contoso.example")

        response = self.client.get(reverse(DETAIL, args=[other.pk]))

        self.assertNotContains(response, "Left-the-organisation notices")
        self.assertEqual(response.context["notice_link"], "")

    def test_the_list_counts_filters_and_explains_the_notices(self):
        self.client.force_login(make_superuser())
        make_row("hard@contoso.example")

        response = self.client.get(reverse(LIST), {"type": "left_org"})

        self.assertEqual([entry["row"].address for entry in response.context["entries"]], [JORDAN])
        self.assertContains(response, "left the organisation 1")
        self.assertNotContains(response, "none counted")
        self.assertContains(
            response, '<option value="left_org" selected>Has a left-the-organisation notice</option>', html=True
        )
        self.assertContains(response, "out-of-office replies never count")

        with_contact = self.client.get(reverse(LIST), {"type": "left_org_contact"})
        self.assertEqual([entry["row"].address for entry in with_contact.context["entries"]], [JORDAN])
        self.assertContains(with_contact, "Notice contact: review")

    def test_direct_pages_and_exports_hide_hints_at_expiry_before_the_next_count(self):
        self.client.force_login(make_superuser())
        expiry = timezone.now()
        BouncedAddress.objects.filter(pk=self.row.pk).update(left_org_hint_expires_at=expiry)
        export_url = reverse("admin:mail_email_monitoring_addresses_export")
        with patch("django.utils.timezone.now", return_value=expiry):
            detail = self.client.get(reverse(DETAIL, args=[self.row.pk]))
            confirmation = self.client.post(reverse(ACTION, args=[self.row.pk, "replace"]), {"step": "confirm"})
            export = self.client.get(export_url)
            filtered = self.client.get(export_url, {"type": "left_org_contact"})
        self.assertContains(detail, "Left-the-organisation notices")
        for value in (
            RILEY,
            "Riley Chen",
            "+12095550123",
            "Contact details need manual review.",
            "open it in the helpdesk",
        ):
            self.assertNotContains(detail, value)
        self.assertNotContains(confirmation, RILEY)
        book = load_workbook(BytesIO(export.content), read_only=True)
        header, data = book.active.values
        record = dict(zip(header, data, strict=True))
        for column in ("Address the notice names", "Name in latest notice", "Phone in latest notice"):
            self.assertIsNone(record.get(column))
        self.assertEqual((record["Left-org notices"], record["Notice contact needs review"]), (1, "No"))
        filtered_book = load_workbook(BytesIO(filtered.content), read_only=True)
        self.assertEqual(len(list(filtered_book.active.values)), 1)

    def test_the_replace_page_hints_at_the_named_address_and_fills_in_nothing(self):
        self.client.force_login(make_superuser())

        response = self.client.post(reverse(ACTION, args=[self.row.pk, "replace"]), {"step": "confirm"})

        self.assertContains(response, f"names <strong>{RILEY}</strong> (who to contact instead, the notice says)")
        self.assertContains(response, "is not verified: confirm it with the member or their organisation")
        self.assertContains(response, '<input type="email" name="new_address" value="" required maxlength="254"')
