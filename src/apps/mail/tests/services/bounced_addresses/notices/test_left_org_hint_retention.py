"""Unverified contact hints expire independently of aggregate notice evidence."""

import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings

from apps.mail.models import BouncedAddress
from apps.mail.services.email_monitoring.addresses import aggregate
from apps.mail.services.email_monitoring.addresses.aggregate import notices

from ..helpers import count_now
from .test_left_org_notices import JORDAN, make_notice

retention_migration = importlib.import_module("apps.mail.migrations.0030_bouncedaddress_hint_retention")


class HintRetentionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_contact_hints_expire_but_aggregate_evidence_remains(self):
        notice = make_notice(
            named_contact="riley@contoso.example",
            named_contact_kind="contact",
            named_contact_name="Riley Chen",
            named_contact_phone="+12095550123",
        )
        config = {**settings.EMAIL_MONITORING, "left_org_hint_retention_days": 30}
        with override_settings(EMAIL_MONITORING=config):
            count_now()

        row = BouncedAddress.objects.get(address=JORDAN)
        expires_at = notice.processed_at + timedelta(days=30)
        self.assertEqual(notices.purge_expired_hints(now=expires_at - timedelta(seconds=1)), 0)
        with patch.object(notices.timezone, "now", return_value=expires_at):
            aggregate.run()

        row.refresh_from_db()
        self.assertEqual(
            (row.left_org_count, row.left_org_first_at, row.left_org_last_at),
            (1, notice.received_at, notice.received_at),
        )
        self.assertEqual(
            (
                row.left_org_contact,
                row.left_org_contact_kind,
                row.left_org_contact_name,
                row.left_org_contact_phone,
                row.left_org_ticket,
                row.left_org_hint_source,
                row.left_org_hint_expires_at,
            ),
            ("", "", "", "", None, None, None),
        )

    def test_deleting_the_source_message_immediately_drops_contact_hints(self):
        notice = make_notice(
            named_contact="riley@contoso.example",
            named_contact_kind="contact",
            named_contact_name="Riley Chen",
            named_contact_phone="+12095550123",
        )
        count_now()
        row = BouncedAddress.objects.get(address=JORDAN)

        notice.delete()

        row.refresh_from_db()
        self.assertEqual(row.left_org_count, 1)
        self.assertEqual(
            (
                row.left_org_contact,
                row.left_org_contact_kind,
                row.left_org_contact_name,
                row.left_org_contact_phone,
                row.left_org_ticket,
                row.left_org_hint_source,
                row.left_org_hint_expires_at,
            ),
            ("", "", "", "", None, None, None),
        )

    def test_persistence_normalizes_old_us_phone_hints_and_rejects_international_ones(self):
        make_notice("us@example.com", named_contact_phone="(209) 555-0123")
        make_notice("uk@example.com", named_contact_phone="+44 207 946 0958")

        count_now()

        phones = dict(BouncedAddress.objects.values_list("address", "left_org_contact_phone"))
        self.assertEqual(phones, {"us@example.com": "+12095550123", "uk@example.com": ""})

    def test_migration_reverse_clears_hints_before_dropping_retention_metadata(self):
        make_notice(
            named_contact="riley@contoso.example",
            named_contact_kind="contact",
            named_contact_name="Riley Chen",
            named_contact_phone="+12095550123",
        )
        count_now()
        operation = retention_migration.Migration.operations[-1]
        self.assertIs(operation.reverse_code, retention_migration.clear_untracked_hints)

        retention_migration.clear_untracked_hints(apps, SimpleNamespace(connection=connection))

        row = BouncedAddress.objects.get(address=JORDAN)
        self.assertEqual(
            (row.left_org_contact, row.left_org_contact_kind, row.left_org_contact_name, row.left_org_contact_phone),
            ("", "", "", ""),
        )
        self.assertIsNone(row.left_org_ticket)
