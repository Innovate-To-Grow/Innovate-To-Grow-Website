"""Turning personal SMS sign-in links off revokes them for good (Hongzhe's decision on #731).

Every outstanding personal link is revoked in the transaction of the write that turns them off, and the SMS Settings
epoch moves on, so a link issued before never signs anyone in again: not when the switch is turned on again, not when
its own row is edited back, and not when it was being stored while the switch went off. A revoked link opens the
normal sign-in page and signs nobody in. Shared links are not affected. Each revocation is audited (who, when, how
many). AWS is never called.
"""

from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkRevocation, SmsLinkToken
from apps.mail.models.sms_config import revoke_personal_links
from apps.mail.services.sms import links, ticket
from apps.mail.services.sms.compose import CampaignLinks

from .policy_helpers import add_phone, sms_settings

PHONE = "+12095550101"
SIGN_IN_PAGE = "/login?returnTo=/subscribe"
MODEL_LOG = "apps.mail.models.sms_config"
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


class TurnedOffOutsideTheAppTests(RevocationTestCase):
    def test_a_link_opened_while_off_revokes_every_outstanding_one(self):
        token, other = self.issue(), self.issue()
        set_outside_the_app(False)
        self.assertFalse(SmsLinkRevocation.objects.exists())

        with self.assertLogs(MODEL_LOG, level="WARNING") as logs:
            opened = self.assert_lands_on_sign_in_page(token)

        self.assertEqual(opened.reason, "switched_off")
        self.assertIn("found_off (link_opened)", "\n".join(logs.output))
        revocation = SmsLinkRevocation.objects.get()
        self.assertEqual(
            (revocation.reason, revocation.via, revocation.actor, revocation.revoked_count),
            (Reason.FOUND_OFF, Via.LINK_OPENED, None, 2),
        )
        set_outside_the_app(True)
        for each in (token, other):
            self.assert_lands_on_sign_in_page(each)

    def test_turning_them_on_again_revokes_the_links_left_live(self):
        token = self.issue()
        set_outside_the_app(False, column="links_enabled")
        with self.assertLogs(MODEL_LOG, level="WARNING"):
            config = sms_settings(links_enabled=True)
        self.assertEqual((config.revocation.reason, config.revocation.revoked_count), (Reason.FOUND_OFF, 1))
        self.assert_lands_on_sign_in_page(token)

    def test_settling_without_a_settings_row_changes_nothing(self):
        token = self.issue()
        SmsConfig.objects.all().delete()
        self.assertEqual(revoke_personal_links(via=Via.LINK_OPENED), (0, None))
        self.assertIsNone(row_of(token).revoked_at)
        self.assertFalse(SmsLinkRevocation.objects.exists())

    def test_settling_while_they_are_on_changes_nothing(self):
        token = self.issue()
        epoch = current_epoch()
        settled = revoke_personal_links(via=Via.LINK_OPENED)
        self.assertEqual((settled.epoch, settled.revocation), (epoch, None))
        self.assertEqual(links.open_link(token).kind, "sign_in")


class IssueRaceTests(RevocationTestCase):
    def test_a_link_stored_while_the_switch_goes_off_never_signs_in(self):
        real_token = links._new_token

        def switch_off_then_token():
            # The switch goes off after the issuer read it as on, before the link is stored.
            sms_settings(personal_links_enabled=False)
            return real_token()

        with patch.object(links, "_new_token", side_effect=switch_off_then_token):
            token = self.issue()

        row = row_of(token)
        # The revocation's sweep ran before this link existed, so its row looks live: its epoch is what stops it.
        self.assertIsNone(row.revoked_at)
        self.assertGreater(row.expires_at, timezone.now())
        self.assertLess(row.epoch, current_epoch())
        self.assertEqual(SmsLinkRevocation.objects.get().revoked_count, 0)
        self.assert_lands_on_sign_in_page(token)
        sms_settings(personal_links_enabled=True)
        self.assert_lands_on_sign_in_page(token)
        row.refresh_from_db()
        self.assertIsNone(row.first_used_at)
        # Turning them on again tidies its row too; it never worked, so no revocation counts it.
        self.assertIsNotNone(row.revoked_at)
        self.assertEqual(SmsLinkRevocation.objects.get().revoked_count, 0)

    def test_a_campaign_already_sending_texts_the_sign_in_page_link_once_they_are_off(self):
        campaign = SmsCampaign.objects.create(message="Hi {{login_link}}", audience_type="all_members")
        campaign_links = CampaignLinks(campaign, SmsConfig.load())  # read while they were on
        sms_settings(personal_links_enabled=False)

        values = campaign_links.values({"member_id": self.member.pk, "phone": PHONE})

        shared = SmsLinkToken.objects.get()
        self.assertIsNone(shared.member_id)
        self.assertEqual(values["login_link"], links.link_url(shared.public_token))

    def test_a_ticket_text_gets_the_sign_in_page_link_once_they_are_off(self):
        event = make_event()
        registration = make_registration(self.member, event, make_ticket(event))
        config = SmsConfig.load()  # read while they were on
        sms_settings(personal_links_enabled=False)

        url = ticket._ticket_link(registration, config, PHONE)

        row = SmsLinkToken.objects.get(registration=registration)
        self.assertIsNone(row.member_id)
        self.assertEqual(links.open_link(token_of(url)).kind, "redirect")


class OpenRaceTests(RevocationTestCase):
    def test_a_revocation_that_commits_while_a_link_is_opened_wins(self):
        token = self.issue()
        real_claim = links._claim

        def revoke_then_claim(link):
            # The switch-off commits after the opener's checks, just before its claim.
            sms_settings(personal_links_enabled=False)
            return real_claim(link)

        with patch.object(links, "_claim", side_effect=revoke_then_claim):
            opened = self.assert_lands_on_sign_in_page(token)

        self.assertEqual(opened.reason, "revoked")
        row = row_of(token)
        self.assertEqual((row.first_used_at, row.use_count), (None, 0))
        self.assertIsNotNone(row.revoked_at)

    def test_a_link_used_before_the_switch_goes_off_stays_used(self):
        token = self.issue()
        self.assertEqual(links.open_link(token).kind, "sign_in")
        sms_settings(personal_links_enabled=False)
        self.assertEqual(SmsLinkRevocation.objects.get().revoked_count, 0)
        row = row_of(token)
        self.assertIsNone(row.revoked_at)
        self.assertIsNotNone(row.first_used_at)

    def test_a_second_click_still_hears_already_used(self):
        token = self.issue()
        self.assertEqual(links.open_link(token).kind, "sign_in")
        self.assertEqual(links.open_link(token).code, "already_used")


class RevocationRecordTests(TestCase):
    def test_a_revocation_describes_itself(self):
        revocation = SmsLinkRevocation(reason=Reason.LINKS_OFF, revoked_count=3, epoch=4)
        self.assertEqual(str(revocation), "Links in SMS turned off: 3 link(s) revoked")

    def test_the_actor_label_falls_back_to_what_is_known(self):
        member = make_member(email="cy@example.com")
        sms_settings(links_enabled=True, personal_links_enabled=True)
        config = SmsConfig.load()
        config.links_enabled = False
        config.save(actor=member, via=Via.ADMIN)
        self.assertEqual(config.revocation.actor_label, "cy@example.com")
