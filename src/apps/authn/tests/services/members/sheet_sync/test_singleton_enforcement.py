import importlib
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone, Member, MemberSheetSyncConfig
from apps.authn.tests.services.members.sheet_sync.test_member_sheet_sync import _enable_config
from apps.core.models import BackgroundJob


class SingletonEnforcementTests(TestCase):
    def test_load_does_not_fall_back_to_disabled_config(self):
        stale = MemberSheetSyncConfig.objects.create(
            is_enabled=False,
            google_sheet_id="stale-sheet",
        )

        loaded = MemberSheetSyncConfig.load()

        self.assertNotEqual(loaded.pk, stale.pk)
        self.assertTrue(loaded._state.adding)
        self.assertFalse(loaded.is_configured)

    def test_saving_enabled_config_disables_others(self):
        first = MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="sheet-a")
        second = MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="sheet-b")
        first.refresh_from_db()
        self.assertFalse(first.is_enabled)
        self.assertTrue(second.is_enabled)

    def test_saving_disabled_config_leaves_others_alone(self):
        enabled = MemberSheetSyncConfig.objects.create(is_enabled=True, google_sheet_id="sheet-a")
        MemberSheetSyncConfig.objects.create(is_enabled=False, google_sheet_id="sheet-b")
        enabled.refresh_from_db()
        self.assertTrue(enabled.is_enabled)

    def test_migration_preserves_all_disabled_configs(self):
        older = MemberSheetSyncConfig.objects.create(is_enabled=False, google_sheet_id="sheet-a")
        newer = MemberSheetSyncConfig.objects.create(is_enabled=False, google_sheet_id="sheet-b")
        now = timezone.now()
        MemberSheetSyncConfig.objects.filter(pk=older.pk).update(updated_at=now - timedelta(days=1))
        MemberSheetSyncConfig.objects.filter(pk=newer.pk).update(updated_at=now)
        normalize = importlib.import_module("apps.authn.migrations.0017_auth_security_invariants").normalize_singletons

        normalize(apps, None)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertFalse(older.is_enabled)
        self.assertFalse(newer.is_enabled)


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DurableFollowUpTests(TestCase):
    def setUp(self):
        _enable_config()

    def test_change_during_processing_creates_follow_up_job(self):
        from apps.authn.services.members.sheet_sync import schedule_member_sync

        schedule_member_sync()
        first = BackgroundJob.objects.get()
        BackgroundJob.objects.filter(pk=first.pk).update(
            status=BackgroundJob.Status.PROCESSING,
            claim_token=BackgroundJob.new_claim_token(),
        )

        schedule_member_sync()

        self.assertEqual(BackgroundJob.objects.count(), 2)
        self.assertEqual(
            BackgroundJob.objects.filter(status=BackgroundJob.Status.PENDING).count(),
            1,
        )


class SignalSchedulingTests(TransactionTestCase):
    """post_save / post_delete on Member, ContactEmail, ContactPhone fire schedule_member_sync."""

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_member_save_triggers_schedule(self, mock_schedule):
        Member.objects.create_user(password="TestPass123!", first_name="Sig", last_name="Nal")
        self.assertTrue(mock_schedule.called)

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_member_delete_triggers_schedule(self, mock_schedule):
        member = Member.objects.create_user(password="TestPass123!", first_name="Del", last_name="Me")
        mock_schedule.reset_mock()
        member.delete()
        self.assertTrue(mock_schedule.called)

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_contact_email_save_triggers_schedule(self, mock_schedule):
        member = Member.objects.create_user(password="TestPass123!", first_name="Ce", last_name="Mail")
        mock_schedule.reset_mock()
        ContactEmail.objects.create(member=member, email_address="ce@example.com", email_type="primary")
        self.assertTrue(mock_schedule.called)

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_contact_phone_save_triggers_schedule(self, mock_schedule):
        member = Member.objects.create_user(password="TestPass123!", first_name="Ph", last_name="One")
        mock_schedule.reset_mock()
        ContactPhone.objects.create(member=member, phone_number="2095551234", region="1-US")
        self.assertTrue(mock_schedule.called)
