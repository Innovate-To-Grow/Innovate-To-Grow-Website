"""The AWS opted-out list sync: what each outcome records, how a complete read reconciles the list (and a partial one
does not clear), and that it never subscribes anyone again. AWS is replaced by the reader's result (the read itself
is covered against botocore's stubbed client in core)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.services.aws.credentials import AwsCredentialsError
from apps.core.services.aws.sms_opt_outs import OptedOutList, OptedOutNumber, OptOutListError
from apps.event.tests.helpers import make_member
from apps.mail.models import SmsOptOut, SmsOptOutSyncState
from apps.mail.services.sms import opt_out_sync

from .policy_helpers import ORIGINATION, add_phone, opt_out, sms_aws_config, sms_settings

READ = "apps.mail.services.sms.opt_out_sync.read_opted_out_list"
RUN_AT = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
STOPPED_AT = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def listing(*numbers, complete=True, list_name="Default"):
    return OptedOutList(
        list_name=list_name,
        numbers=tuple(OptedOutNumber(number, STOPPED_AT, True) for number in numbers),
        complete=complete,
    )


class SyncOutcomeTests(TestCase):
    def test_without_aws_credentials_nothing_is_read(self):
        with patch(READ) as read:
            result = opt_out_sync.sync_opt_outs(now=RUN_AT)
        read.assert_not_called()
        self.assertEqual(result.status, "not_configured")
        state = SmsOptOutSyncState.load()
        self.assertEqual((state.status, state.last_run_at, state.last_success_at), ("not_configured", RUN_AT, None))

    def test_credentials_that_cannot_be_resolved_are_not_configured(self):
        sms_aws_config()
        with patch(READ, side_effect=AwsCredentialsError("missing")):
            self.assertEqual(opt_out_sync.sync_opt_outs(now=RUN_AT).status, "not_configured")

    def test_an_aws_refusal_is_recorded_with_its_code_and_changes_nothing(self):
        sms_aws_config()
        opt_out("+12095550101")
        with patch(READ, side_effect=OptOutListError("AWS refused to read the opted-out list.", code="AccessDenied")):
            with self.assertLogs("apps.mail.services.sms.opt_out_sync", level="WARNING"):
                result = opt_out_sync.sync_opt_outs(now=RUN_AT)
        self.assertEqual(result.status, "failed")
        state = SmsOptOutSyncState.load()
        self.assertEqual(state.status, "failed")
        self.assertIn("AccessDenied", state.message)
        self.assertTrue(SmsOptOut.objects.get().is_active)

    @override_settings(
        SMS_POLICY={
            "link_token_bytes": 16,
            "link_max_validity_days": 14,
            "opt_out_page_size": 25,
            "opt_out_max_pages": 3,
            "opt_out_request_timeout_seconds": 4,
        }
    )
    def test_the_read_uses_the_sending_number_staff_list_and_settings_bounds(self):
        sms_aws_config()
        sms_settings(opt_out_list_name="  I2G  ")
        with patch(READ, return_value=listing()) as read:
            opt_out_sync.sync_opt_outs(now=RUN_AT)
        read.assert_called_once_with(origination=ORIGINATION, list_name="I2G", page_size=25, max_pages=3, timeout=4)

    def test_the_scheduled_run_respects_the_switch(self):
        sms_settings(opt_out_sync_enabled=False)
        with patch.object(opt_out_sync, "sync_opt_outs") as sync:
            self.assertIsNone(opt_out_sync.run_scheduled())
        sync.assert_not_called()
        sms_settings(opt_out_sync_enabled=True)
        with patch.object(opt_out_sync, "sync_opt_outs", return_value="ran") as sync:
            self.assertEqual(opt_out_sync.run_scheduled(should_stop=lambda: False), "ran")
        sync.assert_called_once_with()


class SyncReconcileTests(TestCase):
    def setUp(self):
        sms_aws_config()
        self.member = make_member(email="ada@example.com")
        self.phone = add_phone(self.member, "2095550101")

    def sync(self, result, *, at=RUN_AT):
        with patch(READ, return_value=result):
            return opt_out_sync.sync_opt_outs(now=at)

    def test_a_listed_number_is_added_and_its_phone_unsubscribed(self):
        result = self.sync(listing("+12095550101", "(209) 555-0102", "not-a-number", "+12095550101"))

        self.assertEqual((result.status, result.listed, result.added, result.cleared), ("ok", 2, 2, 0))
        row = SmsOptOut.objects.get(phone_number="+12095550101")
        self.assertEqual((row.source, row.opted_out_at, row.end_user_opted_out), ("aws", STOPPED_AT, True))
        self.assertEqual(row.last_seen_in_aws_at, RUN_AT)
        self.assertIsNotNone(row.contacts_unsubscribed_at)
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.subscribe)
        state = SmsOptOutSyncState.load()
        self.assertEqual((state.status, state.listed_count, state.added_count), ("ok", 2, 2))
        self.assertEqual((state.list_name, state.last_success_at), ("Default", RUN_AT))

    def test_a_send_refusal_is_confirmed_and_a_cleared_number_reopened(self):
        refusal = opt_out("+12095550101", source="send_refusal", opted_out_at=RUN_AT - timedelta(hours=2))
        cleared = opt_out("+12095550102", cleared_at=RUN_AT - timedelta(days=1), cleared_reason="START")

        result = self.sync(listing("+12095550101", "+12095550102"))

        self.assertEqual(result.added, 1)
        refusal.refresh_from_db()
        cleared.refresh_from_db()
        self.assertEqual(refusal.source, "aws")
        self.assertEqual(refusal.last_seen_in_aws_at, RUN_AT)
        self.assertIsNone(cleared.cleared_at)
        self.assertEqual((cleared.source, cleared.cleared_reason), ("aws", ""))

    def test_a_complete_read_clears_numbers_aws_no_longer_lists_but_never_staff_or_newer_ones(self):
        gone = opt_out("+12095550101", last_seen_in_aws_at=RUN_AT - timedelta(hours=1))
        old_refusal = opt_out("+12095550102", source="send_refusal", opted_out_at=RUN_AT - timedelta(days=2))
        new_refusal = opt_out("+12095550103", source="send_refusal", opted_out_at=RUN_AT + timedelta(seconds=5))
        staff = opt_out("+12095550104", source="staff")

        result = self.sync(listing())

        self.assertEqual(result.cleared, 2)
        for row in (gone, old_refusal, new_refusal, staff):
            row.refresh_from_db()
        self.assertIsNotNone(gone.cleared_at)
        self.assertIn("opted back in", gone.cleared_reason)
        self.assertIsNotNone(old_refusal.cleared_at)
        self.assertIsNone(new_refusal.cleared_at)
        self.assertIsNone(staff.cleared_at)
        # Opting back in never subscribes the phone again.
        self.phone.refresh_from_db()
        self.assertTrue(self.phone.subscribe)

    def test_a_partial_read_adds_but_clears_nothing(self):
        gone = opt_out("+12095550199")

        result = self.sync(listing("+12095550101", complete=False))

        self.assertEqual((result.status, result.added, result.cleared), ("partial", 1, 0))
        self.assertIn("nothing was cleared", result.message)
        gone.refresh_from_db()
        self.assertTrue(gone.is_active)
        self.assertEqual(SmsOptOutSyncState.load().status, "partial")

    def test_a_number_the_list_lacked_is_kept_once_even_when_a_refusal_raced_it(self):
        listed = listing("+12095550101")
        original = SmsOptOut.objects.bulk_create

        def race(rows, **kwargs):
            opt_out("+12095550101", source="send_refusal", opted_out_at=timezone.now())
            return original(rows, **kwargs)

        with patch.object(SmsOptOut.objects, "bulk_create", side_effect=race):
            self.sync(listed)

        row = SmsOptOut.objects.get(phone_number="+12095550101")
        self.assertEqual(row.source, "aws")
        self.assertEqual(row.last_seen_in_aws_at, RUN_AT)
