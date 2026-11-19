"""Matching Message Trace rows to outgoing emails: by Message-ID, the one-to-one JSON-send inference, the worst status
of several recipients, and pending recipients leaving the status alone."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import OutboundEmail
from apps.core.services.email.graph.tracing.matching import Verdict, match_rows, parse_rows
from apps.core.tests.services.email_monitoring.helpers import make_email

from . import SENDER, trace_row

DeliveryStatus = OutboundEmail.DeliveryStatus


class MatchingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.accepted = timezone.now() - timedelta(hours=2)

    def email(self, message_id="<m1@ucmerced.edu>", recipients=("person@example.com",), **values):
        return make_email(
            mailbox=SENDER,
            internet_message_id=message_id,
            recipient=recipients[0],
            recipients=list(recipients),
            recipient_count=len(recipients),
            accepted_at=values.pop("accepted_at", self.accepted),
            **values,
        )

    def row(self, message_id="<m1@ucmerced.edu>", minutes=1, **values):
        return trace_row(message_id, received=self.accepted + timedelta(minutes=minutes), **values)

    def match(self, emails, rows, *, complete=True):
        found = match_rows(list(emails), parse_rows(rows), complete=complete)
        return {pk: verdict for pk, (_email, verdict) in found.items()}

    def test_the_message_id_is_compared_exactly(self):
        email = self.email()
        self.assertEqual(self.match([email], [self.row()]), {email.pk: Verdict("delivered", "delivered")})
        self.assertEqual(self.match([email], [self.row("<M1@ucmerced.edu>"), self.row("m1@ucmerced.edu")]), {})

    def test_each_trace_status_maps_to_its_delivery_status(self):
        email = self.email()
        cases = {
            "delivered": DeliveryStatus.DELIVERED,
            "expanded": DeliveryStatus.DELIVERED,
            "failed": DeliveryStatus.FAILURE_CONFIRMED,
            "quarantined": DeliveryStatus.QUARANTINED,
            "filteredAsSpam": DeliveryStatus.FILTERED_AS_SPAM,
        }
        for status, expected in cases.items():
            with self.subTest(status):
                self.assertEqual(self.match([email], [self.row(status=status)]), {email.pk: Verdict(expected, status)})

    def test_a_pending_recipient_changes_nothing(self):
        email = self.email(recipients=("a@example.com", "b@example.com"))
        for pending in ("pending", "gettingStatus", "notKnownYet"):
            rows = [self.row(recipient="a@example.com"), self.row(recipient="b@example.com", status=pending)]
            with self.subTest(pending):
                self.assertEqual(self.match([email], rows), {email.pk: Verdict(None, pending)})

    def test_several_recipients_take_the_worst_status(self):
        email = self.email(recipients=("a@example.com", "b@example.com", "c@example.com"))
        rows = [
            self.row(recipient="a@example.com"),
            self.row(recipient="b@example.com", status="failed"),
            self.row(recipient="c@example.com", status="filteredAsSpam"),
        ]
        self.assertEqual(self.match([email], rows), {email.pk: Verdict("failure_confirmed", "failed")})
        rows[1]["status"] = "delivered"
        self.assertEqual(self.match([email], rows), {email.pk: Verdict("filtered_as_spam", "filteredAsSpam")})

    def test_a_recipient_not_in_the_trace_yet_changes_nothing(self):
        email = self.email(recipients=("a@example.com", "b@example.com"))
        self.assertEqual(self.match([email], [self.row(recipient="a@example.com")]), {})

    def test_a_json_send_is_inferred_when_the_pair_is_unique(self):
        email = self.email(message_id="")
        rows = [self.row("<json1@namprd.outlook.com>", minutes=3)]

        self.assertEqual(self.match([email], rows), {email.pk: Verdict("delivered", "delivered")})
        self.assertEqual(self.match([email], rows, complete=False), {})  # a partly read window hides rivals

    def test_the_inference_needs_the_same_recipient_subject_and_time(self):
        email = self.email(message_id="")
        for row in (
            self.row("<j@x>", recipient="other@example.com"),
            self.row("<j@x>", subject="Another subject"),
            self.row("<j@x>", minutes=-3),
            self.row("<j@x>", minutes=11),
            self.row("<j@x>", receivedDateTime="never"),
        ):
            with self.subTest(row=row["recipientAddress"] + row["subject"] + row["receivedDateTime"]):
                self.assertEqual(self.match([email], [row]), {})

    def test_an_ambiguous_inference_matches_nothing(self):
        first = self.email(message_id="")
        second = self.email(message_id="", accepted_at=self.accepted + timedelta(minutes=2))
        self.assertEqual(self.match([first, second], [self.row("<j1@x>", minutes=3)]), {})
        # Two traced messages that fit one email: neither is chosen.
        self.assertEqual(self.match([first], [self.row("<j1@x>", minutes=1), self.row("<j2@x>", minutes=4)]), {})

    def test_a_traced_message_id_the_site_knows_is_never_inferred_onto_another_email(self):
        json_email = self.email(message_id="")
        self.email(message_id="<known@ucmerced.edu>", status=OutboundEmail.Status.FAILED)

        self.assertEqual(self.match([json_email], [self.row("<known@ucmerced.edu>")]), {})
