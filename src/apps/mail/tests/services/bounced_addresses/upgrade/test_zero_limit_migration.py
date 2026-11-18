"""Round-trip coverage for the 0 KB receiving-limit upgrade migration."""

import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from apps.core.services.email.bounces.classify import classify


class ZeroLimitMigrationRoundTripTests(TransactionTestCase):
    BEFORE = ("mail", "0028_bounced_address_notice_contact_hints")
    AFTER = ("mail", "0029_alter_bouncedaddress_suggestion")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_forward_and_reverse_restore_consistent_classification_without_losing_review_state(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.BEFORE])
        before_apps = executor.loader.project_state([self.BEFORE]).apps
        Bounce = before_apps.get_model("core", "EmailBounce")
        Outbound = before_apps.get_model("core", "OutboundEmail")
        Address = before_apps.get_model("mail", "BouncedAddress")
        State = before_apps.get_model("mail", "BounceAggregationState")

        outbound = Outbound.objects.create(category="campaign", bounce_classification="hard")
        bounce = Bounce.objects.create(
            dedupe_key=uuid.uuid4().hex,
            mailbox="sender@example.org",
            ndr_graph_id="zero-limit-report",
            received_at=timezone.now(),
            recipient="limited@example.org",
            diagnostic_code="550 5.2.3 Mailbox disabled; Max size allowed: 0 KB",
            status_code="5.2.3",
            classification="hard",
            category="mailbox_disabled",
            is_permanent=True,
            reason="Recipient mailbox accepts no messages (0 KB size limit): treated as disabled",
            email_id=outbound.pk,
        )
        Bounce.objects.create(
            dedupe_key=uuid.uuid4().hex,
            mailbox="sender@example.org",
            ndr_graph_id="unknown-report",
            received_at=timezone.now(),
            recipient="limited@example.org",
            classification="unknown",
            category="unknown",
            email_id=outbound.pk,
        )
        preexisting_transient = Bounce.objects.create(
            dedupe_key=uuid.uuid4().hex,
            mailbox="sender@example.org",
            ndr_graph_id="already-transient-zero-limit-report",
            received_at=timezone.now(),
            recipient="temporary@example.org",
            diagnostic_code="450 Maximum message size is 0 KB while maintenance runs",
            status_code="4.3.0",
            classification="soft",
            category="transient",
            is_permanent=False,
            reason="Temporary receiving-service maintenance",
        )
        address = Address.objects.create(
            address="limited@example.org",
            status="dismissed",
            suppression="undeliverable",
            suppressed_at=timezone.now(),
            left_org_contact_name="Casey Example",
            left_org_contact_phone="+12025550123",
        )
        cursor = (timezone.now(), uuid.uuid4())
        State.objects.create(source="graph", cursor_at=cursor[0], cursor_id=cursor[1], processed_total=7)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.AFTER])
        after_apps = executor.loader.project_state([self.AFTER]).apps
        migrated_bounce = after_apps.get_model("core", "EmailBounce").objects.get(pk=bounce.pk)
        migrated_outbound = after_apps.get_model("core", "OutboundEmail").objects.get(pk=outbound.pk)
        self.assertEqual(
            (
                migrated_bounce.category,
                migrated_bounce.classification,
                migrated_bounce.is_permanent,
                migrated_bounce.reason,
            ),
            (
                "transient",
                "soft",
                False,
                "Recipient mailbox reports a 0 KB limit; retry after the receiving service is fixed",
            ),
        )
        self.assertEqual(migrated_outbound.bounce_classification, "soft")
        state = after_apps.get_model("mail", "BounceAggregationState").objects.get(source="graph")
        self.assertEqual((state.cursor_at, state.cursor_id), cursor)

        # A genuine temporary failure written by the new runtime uses the same reason as upgraded rows.
        diagnostic = "450 4.3.0 Maximum message size is 0 KB while maintenance runs"
        verdict = classify("failed", "4.3.0", diagnostic)
        late = after_apps.get_model("core", "EmailBounce").objects.create(
            dedupe_key=uuid.uuid4().hex,
            mailbox="test@example.org",
            ndr_graph_id="during-new-release",
            received_at=timezone.now(),
            recipient="valid@example.org",
            action="failed",
            status_code="4.3.0",
            diagnostic_code=diagnostic,
            classification=verdict.classification,
            category=verdict.category,
            is_permanent=verdict.is_permanent,
            reason=verdict.reason,
        )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.BEFORE])
        rolled_back_apps = executor.loader.project_state([self.BEFORE]).apps
        rolled_back_bounce = rolled_back_apps.get_model("core", "EmailBounce").objects.get(pk=bounce.pk)
        rolled_back_outbound = rolled_back_apps.get_model("core", "OutboundEmail").objects.get(pk=outbound.pk)
        unchanged_transient = rolled_back_apps.get_model("core", "EmailBounce").objects.get(pk=preexisting_transient.pk)
        self.assertEqual(
            (
                rolled_back_bounce.category,
                rolled_back_bounce.classification,
                rolled_back_bounce.is_permanent,
                rolled_back_bounce.reason,
            ),
            (
                "mailbox_disabled",
                "hard",
                True,
                "Recipient mailbox accepts no messages (0 KB size limit): treated as disabled",
            ),
        )
        self.assertEqual(rolled_back_outbound.bounce_classification, "hard")
        self.assertEqual(
            (
                unchanged_transient.category,
                unchanged_transient.classification,
                unchanged_transient.is_permanent,
                unchanged_transient.reason,
            ),
            ("transient", "soft", False, "Temporary receiving-service maintenance"),
        )
        rolled_back_state = rolled_back_apps.get_model("mail", "BounceAggregationState").objects.get(source="graph")
        self.assertEqual((rolled_back_state.cursor_at, rolled_back_state.cursor_id), cursor)
        late = rolled_back_apps.get_model("core", "EmailBounce").objects.get(pk=late.pk)
        self.assertEqual((late.category, late.classification, late.is_permanent), ("transient", "soft", False))
        rolled_back_address = rolled_back_apps.get_model("mail", "BouncedAddress").objects.get(pk=address.pk)
        self.assertEqual(
            (
                rolled_back_address.status,
                rolled_back_address.suppression,
                rolled_back_address.suppressed_at,
                rolled_back_address.left_org_contact_name,
                rolled_back_address.left_org_contact_phone,
            ),
            (
                "dismissed",
                "undeliverable",
                address.suppressed_at,
                "Casey Example",
                "+12025550123",
            ),
        )
