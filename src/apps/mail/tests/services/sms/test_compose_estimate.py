"""What one text says (names, links, the opt-out footer), when a campaign cannot be sent, and the segment and cost
estimate (with the composer's settings)."""

from decimal import Decimal

from django.test import TestCase, override_settings

from apps.event.tests.helpers import make_event, make_member, make_superuser
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkToken
from apps.mail.services.sms import compose, estimate
from apps.mail.services.sms.errors import LinksDisabled, SmsSendRefused

from .policy_helpers import sms_settings

FOOTER = "Reply STOP to opt out."


def recipient(member=None, phone="+12095550101", first="Ada"):
    return {
        "member_id": member.pk if member else None,
        "phone": phone,
        "first_name": first,
        "last_name": "Lovelace",
        "full_name": f"{first} Lovelace",
    }


class FooterTests(TestCase):
    def test_the_footer_is_added_on_its_own_line_unless_the_text_says_stop(self):
        config = SmsConfig.load()
        self.assertEqual(compose.apply_footer("Hello  \n", config), f"Hello\n{FOOTER}")
        self.assertEqual(compose.apply_footer("Text STOP to quit", config), "Text STOP to quit")
        self.assertEqual(compose.apply_footer("Reply stop.", config), "Reply stop.")
        self.assertEqual(compose.apply_footer("We stopped by", config), f"We stopped by\n{FOOTER}")

    def test_staff_can_turn_it_off(self):
        config = sms_settings(footer_enabled=False)
        self.assertEqual(compose.apply_footer("Hello", config), "Hello")


@override_settings(FRONTEND_URL="https://i2g.example.edu")
class CampaignTextTests(TestCase):
    def setUp(self):
        self.event = make_event(name="Fall Demo", slug="fall-demo")
        self.member = make_member(email="ada@example.com", first_name="Ada")

    def campaign(self, message, **fields):
        return SmsCampaign.objects.create(message=message, audience_type="all_members", **fields)

    def text(self, campaign, row, config=None):
        config = config or SmsConfig.load()
        return compose.render_campaign_text(campaign, row, links=compose.CampaignLinks(campaign, config), config=config)

    def test_names_and_footer_without_links(self):
        self.assertEqual(self.text(self.campaign("Hi {{ first_name }}"), recipient()), f"Hi Ada\n{FOOTER}")
        self.assertFalse(SmsLinkToken.objects.exists())

    def test_a_link_placeholder_is_refused_while_links_are_off(self):
        campaign = self.campaign("Hi {{login_link}}")
        with self.assertRaises(LinksDisabled):
            self.text(campaign, recipient())
        with self.assertRaises(LinksDisabled):
            compose.refuse_unsendable(campaign)

    def test_generic_links_are_shared_and_return_to_the_campaigns_page(self):
        config = sms_settings(links_enabled=True)
        campaign = self.campaign(
            "{{login_link}} {{ticket_link}} {{event_link}}", login_redirect_path="/subscribe", event=self.event
        )
        first = self.text(campaign, recipient(self.member), config)
        second = self.text(campaign, recipient(phone="+12095550102", first="Bo"), config)

        self.assertEqual(first.split("\n")[0], second.split("\n")[0])
        rows = {row.purpose: row for row in SmsLinkToken.objects.all()}
        self.assertEqual(set(rows), {"login", "ticket", "event"})
        self.assertTrue(all(row.member_id is None and row.public_token for row in rows.values()))
        self.assertEqual(rows["login"].redirect_path, "/login?returnTo=/subscribe")
        self.assertEqual(rows["ticket"].redirect_path, "/login?returnTo=/event-registration%3Fevent%3Dfall-demo")
        self.assertEqual(rows["event"].redirect_path, "/event-registration?event=fall-demo")
        self.assertTrue(first.startswith("https://i2g.example.edu/l/"))

    def test_personal_links_go_only_to_members_who_may_sign_in_by_sms(self):
        config = sms_settings(links_enabled=True, personal_links_enabled=True)
        campaign = self.campaign("{{login_link}}")
        staff = make_superuser()
        self.text(campaign, recipient(self.member), config)
        self.text(campaign, recipient(staff, phone="+12095550102"), config)
        self.text(campaign, recipient(phone="+12095550103"), config)

        personal = SmsLinkToken.objects.get(member__isnull=False)
        self.assertEqual(
            (personal.member, personal.redirect_path, personal.campaign), (self.member, "/account", campaign)
        )
        self.assertEqual(SmsLinkToken.objects.filter(member__isnull=True).count(), 1)

    def test_a_ticket_link_without_an_event_lands_on_the_account(self):
        config = sms_settings(links_enabled=True, personal_links_enabled=True)
        self.text(self.campaign("{{ticket_link}}"), recipient(self.member), config)
        self.assertEqual(SmsLinkToken.objects.get().redirect_path, "/account")

    def test_an_event_link_needs_the_campaigns_event(self):
        sms_settings(links_enabled=True)
        campaign = self.campaign("{{event_link}}")
        with self.assertRaises(SmsSendRefused):
            compose.refuse_unsendable(campaign)
        with self.assertRaises(SmsSendRefused):
            self.text(campaign, recipient())

    def test_the_preview_shows_example_names_links_and_footer(self):
        text = compose.preview_text("Hi {{first_name}}: {{event_link}}", SmsConfig.load(), link="LINK")
        self.assertEqual(text, f"Hi Hongzhe: LINK\n{FOOTER}")


@override_settings(FRONTEND_URL="https://i2g.example.edu")
class EstimateTests(TestCase):
    def test_each_recipients_text_is_measured_as_sent(self):
        config = sms_settings(cost_per_segment=Decimal("0.0100"))
        rows = [recipient(first="Ada"), recipient(first="A" * 140)]

        result = estimate.estimate("Hi {{first_name}}", rows, config, sample=compose.EXAMPLE_NAMES)

        self.assertEqual((result.recipients, result.encoding), (2, "GSM-7"))
        self.assertEqual(result.characters, len(f"Hi Hongzhe\n{FOOTER}"))
        self.assertEqual((result.segments_per_text, result.max_segments_per_text, result.total_segments), (1, 2, 3))
        self.assertEqual(result.cost, Decimal("0.03"))

    def test_one_emoji_makes_the_text_ucs2_and_links_count_full_length(self):
        config = sms_settings(footer_enabled=False)
        message = "Party 🎉 {{event_link}}"
        result = estimate.estimate(message, [recipient()], config, sample=compose.EXAMPLE_NAMES)
        self.assertEqual(result.encoding, "UCS-2")
        expected_chars = len("Party 🎉 ") + len("https://i2g.example.edu/l/") + 22
        self.assertEqual(result.characters, expected_chars)
        self.assertEqual(result.segments_per_text, 1)

    def test_no_recipients_cost_nothing(self):
        result = estimate.estimate("Hi", [], SmsConfig.load(), sample=compose.EXAMPLE_NAMES)
        self.assertEqual((result.total_segments, result.cost, result.max_segments_per_text), (0, Decimal("0.00"), 1))

    def test_the_composer_gets_the_same_footer_link_length_and_price(self):
        settings = estimate.composer_settings(sms_settings(cost_per_segment=Decimal("0.0085")))
        self.assertEqual(settings["footer"], FOOTER)
        self.assertEqual(settings["linkLength"], len("https://i2g.example.edu/l/") + 22)
        self.assertEqual(settings["linkPlaceholders"], ["login_link", "ticket_link", "event_link"])
        self.assertEqual((settings["linksEnabled"], settings["costPerSegment"]), (False, "0.0085"))
        self.assertEqual(estimate.composer_settings(sms_settings(footer_enabled=False))["footer"], "")
