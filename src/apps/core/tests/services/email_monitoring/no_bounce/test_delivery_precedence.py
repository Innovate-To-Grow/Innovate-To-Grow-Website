"""Delivery status precedence: a confirmed failure > quarantined / filtered as spam > delivered > delayed > no bounce
received > unknown. A bounce's confirmed failure replaces any status (a late report overrides "delivered" and "no
bounce received"); a delay report never softens a stronger status, yet still marks an uncertain send."""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, OutboundEmail
from apps.core.services.email.bounces.recording.store import apply_to_email

from ..helpers import make_bounce, make_email

DeliveryStatus = OutboundEmail.DeliveryStatus


class PrecedenceTests(TestCase):
    def setUp(self):
        cache.clear()

    def after(self, start: str, classification: str, **email_values) -> OutboundEmail:
        email = make_email(delivery_status=start, **email_values)
        bounce = make_bounce(classification=classification, email=email, received_at=timezone.now())
        apply_to_email(email.pk, bounce)
        email.refresh_from_db()
        return email

    def test_a_delay_never_softens_a_stronger_status(self):
        for start in (
            DeliveryStatus.DELIVERED,
            DeliveryStatus.QUARANTINED,
            DeliveryStatus.FILTERED_AS_SPAM,
            DeliveryStatus.FAILURE_CONFIRMED,
        ):
            with self.subTest(start=start):
                self.assertEqual(self.after(start, EmailBounce.Classification.DELAYED).delivery_status, start)

    def test_a_delay_replaces_weaker_statuses_including_an_uncertain_send(self):
        for start in (DeliveryStatus.UNKNOWN, DeliveryStatus.NO_BOUNCE, DeliveryStatus.NOT_APPLICABLE):
            with self.subTest(start=start):
                email = self.after(start, EmailBounce.Classification.DELAYED, status=OutboundEmail.Status.UNCERTAIN)
                self.assertEqual(email.delivery_status, DeliveryStatus.DELAYED)

    def test_a_late_failure_report_overrides_every_status(self):
        for start in (DeliveryStatus.NO_BOUNCE, DeliveryStatus.DELIVERED, DeliveryStatus.QUARANTINED):
            with self.subTest(start=start):
                email = self.after(start, EmailBounce.Classification.HARD)
                self.assertEqual(email.delivery_status, DeliveryStatus.FAILURE_CONFIRMED)
                self.assertEqual(email.bounce_classification, EmailBounce.Classification.HARD)

    def test_stronger_than_follows_the_documented_order(self):
        stronger = DeliveryStatus.stronger_than

        self.assertEqual(
            set(stronger(DeliveryStatus.DELAYED)),
            {"delivered", "filtered_as_spam", "quarantined", "failure_confirmed"},
        )
        self.assertEqual(set(stronger(DeliveryStatus.QUARANTINED)), {"failure_confirmed"})
        self.assertEqual(stronger(DeliveryStatus.FAILURE_CONFIRMED), [])
        self.assertNotIn("no_bounce", stronger(DeliveryStatus.NO_BOUNCE))
        self.assertIn("no_bounce", stronger(DeliveryStatus.UNKNOWN))
        self.assertEqual(
            {value for value, _label in DeliveryStatus.choices},
            set(stronger("unknown")) | {"unknown", "not_applicable"},
        )
