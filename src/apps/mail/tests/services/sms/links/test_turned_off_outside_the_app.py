from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkRevocation, SmsLinkToken
from apps.mail.models.sms.personal_links import revoke_personal_links
from apps.mail.services.sms import links
from apps.mail.services.sms.content.compose import CampaignLinks
from apps.mail.services.sms.delivery import ticket
from apps.mail.tests.services.sms.links.test_link_revocation import (
    MODEL_LOG,
    PHONE,
    Reason,
    RevocationTestCase,
    Via,
    current_epoch,
    row_of,
    set_outside_the_app,
    token_of,
)

from ..policy.policy_helpers import sms_settings


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
        real_token = links.issuing._new_token

        def switch_off_then_token():
            # The switch goes off after the issuer read it as on, before the link is stored.
            sms_settings(personal_links_enabled=False)
            return real_token()

        with patch.object(links.issuing, "_new_token", side_effect=switch_off_then_token):
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
        real_claim = links.opening._claim

        def revoke_then_claim(link):
            # The switch-off commits after the opener's checks, just before its claim.
            sms_settings(personal_links_enabled=False)
            return real_claim(link)

        with patch.object(links.opening, "_claim", side_effect=revoke_then_claim):
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
