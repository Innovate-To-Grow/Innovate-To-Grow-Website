"""Turning personal SMS sign-in links off revokes them for good (Hongzhe's decision on #731).

Every outstanding personal link is revoked in the transaction of the write that turns them off, and the SMS Settings
epoch moves on, so a link issued before never signs anyone in again: not when the switch is turned on again, not when
its own row is edited back, and not when it was being stored while the switch went off. A revoked link opens the
normal sign-in page and signs nobody in. Shared links are not affected. Each revocation is audited (who, when, how
many). AWS is never called.
"""

from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkRevocation, SmsLinkToken
from apps.mail.services.sms import links

from ..policy.policy_helpers import add_phone, sms_settings

PHONE = "+12095550101"
SIGN_IN_PAGE = "/login?returnTo=/subscribe"
MODEL_LOG = "apps.mail.models.sms.personal_links"
Reason = SmsLinkRevocation.Reason
Via = SmsLinkRevocation.Via


def token_of(url):
    return url.rsplit("/l/", 1)[1]


def row_of(token) -> SmsLinkToken:
    return SmsLinkToken.objects.get(token_hash=links.token_digest(token))


def current_epoch() -> int:
    return SmsConfig.load().personal_links_epoch


def set_outside_the_app(value: bool, column="personal_links_enabled"):
    """What a raw SQL change does: no save, no bulk update, so nothing is revoked or recorded."""
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE mail_smsconfig SET {column} = %s", [value])  # noqa: S608 - fixed column names


@override_settings(FRONTEND_URL="https://i2g.example.edu")
class RevocationTestCase(TestCase):
    def setUp(self):
        sms_settings(links_enabled=True, personal_links_enabled=True)
        self.member = make_member(email="ada@example.com", first_name="Ada")
        add_phone(self.member, "2095550101")

    def issue(self, *, member=None, phone=PHONE, redirect_path="/subscribe"):
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN,
            member=member or self.member,
            phone=phone,
            redirect_path=redirect_path,
            validity_days=3,
        )
        return token_of(url)

    def assert_lands_on_sign_in_page(self, token, redirect_to=SIGN_IN_PAGE):
        opened = links.open_link(token)
        self.assertEqual((opened.kind, opened.member, opened.redirect_to), ("redirect", None, redirect_to))
        return opened


class SwitchingOffRevokesForGoodTests(RevocationTestCase):
    def test_turning_personal_links_off_revokes_every_outstanding_one_and_records_who_and_how_many(self):
        bo = make_member(email="bo@example.com")
        add_phone(bo, "2095550102")
        ada_token, bo_token = self.issue(), self.issue(member=bo, phone="+12095550102")
        used_token = self.issue()
        self.assertEqual(links.open_link(used_token).kind, "sign_in")
        old_token = self.issue()
        SmsLinkToken.objects.filter(pk=row_of(old_token).pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        campaign = SmsCampaign.objects.create(message="{{event_link}}", audience_type="all_members")
        shared = token_of(
            links.shared_link(
                campaign=campaign, purpose=links.Purpose.EVENT, redirect_path="/event-registration?e=1", validity_days=3
            )
        )
        redirect = token_of(
            links.issue_redirect_link(purpose=links.Purpose.TICKET, redirect_path="/login", validity_days=3)
        )
        epoch = current_epoch()
        admin = make_superuser()

        config = SmsConfig.load()
        config.personal_links_enabled = False
        config.save(actor=admin, via=Via.ADMIN)

        revocation = SmsLinkRevocation.objects.get()
        self.assertEqual(config.revocation, revocation)
        self.assertEqual(
            (revocation.reason, revocation.via, revocation.actor, revocation.revoked_count, revocation.epoch),
            (Reason.PERSONAL_LINKS_OFF, Via.ADMIN, admin, 2, epoch + 1),
        )
        self.assertIn("admin@example.com", revocation.actor_label)
        self.assertEqual((config.personal_links_epoch, current_epoch()), (epoch + 1, epoch + 1))
        for token in (ada_token, bo_token):
            row = row_of(token)
            self.assertIsNotNone(row.revoked_at)
            self.assertLessEqual(row.expires_at, timezone.now())
        # A used or expired link is not outstanding; shared and redirect links are no credential: none is touched.
        for token in (used_token, old_token, shared, redirect):
            self.assertIsNone(row_of(token).revoked_at)
        self.assertGreater(row_of(shared).expires_at, timezone.now())

        sms_settings(personal_links_enabled=True)

        for token in (ada_token, bo_token):
            self.assert_lands_on_sign_in_page(token)
            row = row_of(token)
            self.assertEqual((row.first_used_at, row.use_count), (None, 0))
        self.assertEqual(links.open_link(shared).redirect_to, "/event-registration?e=1")
        # A link issued after they were turned on again works as usual.
        self.assertEqual(links.open_link(self.issue()).kind, "sign_in")
        self.assertEqual(SmsLinkRevocation.objects.count(), 1)

    def test_turning_links_in_sms_off_revokes_them_too(self):
        token = self.issue()
        sms_settings(links_enabled=False)
        revocation = SmsLinkRevocation.objects.get()
        self.assertEqual((revocation.reason, revocation.via, revocation.actor_label), (Reason.LINKS_OFF, Via.SAVE, ""))
        self.assertEqual(revocation.revoked_count, 1)
        sms_settings(links_enabled=True)
        self.assert_lands_on_sign_in_page(token)

    def test_turning_both_off_at_once_is_one_revocation(self):
        self.issue()
        sms_settings(links_enabled=False, personal_links_enabled=False)
        self.assertEqual(SmsLinkRevocation.objects.get().reason, Reason.PERSONAL_LINKS_OFF)

    def test_a_save_that_keeps_them_on_revokes_nothing(self):
        token = self.issue()
        epoch = current_epoch()
        config = sms_settings(footer_text="Text STOP to opt out.", quiet_hours_enabled=False)
        self.assertIsNone(config.revocation)
        self.assertEqual(current_epoch(), epoch)
        self.assertFalse(SmsLinkRevocation.objects.exists())
        self.assertEqual(links.open_link(token).kind, "sign_in")

    def test_saves_while_they_are_off_record_no_empty_revocation(self):
        self.issue()
        sms_settings(personal_links_enabled=False)
        epoch = current_epoch()
        sms_settings(footer_text="Text STOP to opt out.")
        sms_settings(personal_links_enabled=True)
        self.assertEqual(SmsLinkRevocation.objects.count(), 1)
        self.assertGreater(current_epoch(), epoch)

    def test_a_bulk_update_revokes_like_a_save(self):
        token = self.issue()
        SmsConfig.objects.update(personal_links_enabled=False)
        revocation = SmsLinkRevocation.objects.get()
        self.assertEqual((revocation.via, revocation.actor, revocation.revoked_count), (Via.BULK_UPDATE, None, 1))
        SmsConfig.objects.update(personal_links_enabled=True)
        self.assert_lands_on_sign_in_page(token)

    def test_the_epoch_never_moves_back(self):
        stale = SmsConfig.load()
        token = self.issue()
        sms_settings(personal_links_enabled=False)
        sms_settings(personal_links_enabled=True)
        epoch = current_epoch()
        # A copy loaded before the switch went off and on, saved later, writes its other values but not its epoch.
        stale.footer_text = "Text STOP to opt out."
        stale.save()
        self.assertEqual((current_epoch(), stale.personal_links_epoch), (epoch, epoch))
        # Nor can a bulk update set it back.
        SmsConfig.objects.update(personal_links_epoch=row_of(token).epoch)
        self.assertEqual(current_epoch(), epoch)
        self.assert_lands_on_sign_in_page(token)

    def test_editing_a_revoked_link_back_does_not_revive_it(self):
        token = self.issue()
        sms_settings(personal_links_enabled=False)
        sms_settings(personal_links_enabled=True)
        SmsLinkToken.objects.update(revoked_at=None, expires_at=timezone.now() + timedelta(days=3))
        self.assert_lands_on_sign_in_page(token)
        self.assertIsNone(row_of(token).first_used_at)

    def test_recreating_the_settings_row_never_matches_an_issued_link(self):
        token = self.issue()
        issued = row_of(token).epoch
        SmsConfig.objects.all().delete()
        with self.assertLogs(MODEL_LOG, level="WARNING"):
            sms_settings(links_enabled=True, personal_links_enabled=True)
        self.assertGreater(current_epoch(), issued)
        self.assert_lands_on_sign_in_page(token)
