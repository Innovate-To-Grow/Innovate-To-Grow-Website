"""Mail → Delivery Rates: the seven channel cards, their fields, validation and the live status JSON."""

from decimal import Decimal

from django.utils.html import escape

from apps.core.models.base.delivery_rates import MANUAL_RATE_HELP, SMART_RATE_HELP
from apps.mail.admin.settings.rates.forms import MANUAL_RATE_NOTE
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member

from .delivery_rates_helpers import READ_AT, Channel, DeliveryRatesTestCase

UNIT_SUFFIXES = {
    Channel.GRAPH_SEND: "messages / minute",
    Channel.GRAPH_READ: "requests / minute",
    Channel.SES_SEND: "recipients / second",
    Channel.SMTP_SEND: "messages / minute",
    Channel.GMAIL_IMAP: "sessions / minute",
    Channel.GMAIL_API_SEND: "messages / minute",
    Channel.SMS_SEND: "messages / second",
}
# The Advanced fields each card has (besides the provider rate limit, which every card has).
CHANNEL_FIELDS = {
    Channel.GRAPH_SEND: {
        "daily_limit",
        "hourly_external_limit",
        "hourly_internal_limit",
        "limits_confirmed",
        "budget_headroom",
        "transactional_reserve",
    },
    Channel.GRAPH_READ: set(),
    Channel.SES_SEND: {"daily_limit", "budget_headroom", "transactional_reserve"},
    Channel.SMTP_SEND: {"daily_limit", "daily_message_limit", "budget_headroom", "transactional_reserve"},
    Channel.GMAIL_IMAP: set(),
    Channel.GMAIL_API_SEND: {
        "daily_limit",
        "daily_message_limit",
        "daily_external_limit",
        "internal_domain",
        "budget_headroom",
        "transactional_reserve",
    },
    Channel.SMS_SEND: {"parts_limit", "daily_limit", "budget_headroom", "transactional_reserve"},
}
OPTIONAL = set().union(*CHANNEL_FIELDS.values())


class AccessTests(DeliveryRatesTestCase):
    def test_members_who_are_not_admins_are_refused_everywhere(self):
        member = make_member()
        before = self.policy(Channel.SMS_SEND).manual_rate

        for method, url, data in (
            ("get", self.url, None),
            ("post", self.url, self.post_data(**{"sms_send-manual_rate": "0.5"})),
            ("get", self.status_url, None),
            ("post", "/admin/mail/settings/rates/graph_send/reset/", None),
        ):
            with self.subTest(method=method, url=url):
                assert_refused_to_member(self, url, member, method, data=data or {})
        self.assertEqual(self.policy(Channel.SMS_SEND).manual_rate, before)

    def test_an_admin_opens_the_page(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save delivery rates")
        self.assertContains(response, 'href="/admin/mail/settings/rates/"')  # the Delivery Operations tab
        self.assertContains(response, "admin/js/poll-backoff.js")  # status refreshes back off on 429


class CardTests(DeliveryRatesTestCase):
    def test_seven_cards_with_the_exact_help_texts(self):
        response = self.client.get(self.url)

        self.assertContains(response, '<article id="rate-card-', count=7)
        self.assertContains(response, escape(SMART_RATE_HELP), count=7)
        self.assertContains(response, escape(MANUAL_RATE_HELP), count=7)
        for channel in Channel.values:
            with self.subTest(channel=channel):
                html = self.card_html(response, channel)
                self.assertIn(self.policy(channel).get_channel_display(), html)
                self.assertIn(f'name="{channel}-smart_enabled"', html)
                self.assertIn(f'name="{channel}-manual_rate"', html)
                self.assertIn("Advanced: provider limits", html)

    def test_each_manual_rate_shows_its_unit_suffix(self):
        response = self.client.get(self.url)

        for channel, suffix in UNIT_SUFFIXES.items():
            with self.subTest(channel=channel):
                html = self.card_html(response, channel)
                manual = html[html.index(f'name="{channel}-manual_rate"') :]
                self.assertIn(suffix, manual[: manual.index("</div>") + 200])

    def test_channel_specific_fields_appear_only_on_their_channels(self):
        response = self.client.get(self.url)

        for channel, fields in CHANNEL_FIELDS.items():
            html = self.card_html(response, channel)
            self.assertIn(f'name="{channel}-provider_limit"', html)
            for name in OPTIONAL:
                with self.subTest(channel=channel, field=name):
                    self.assertEqual(f'name="{channel}-{name}"' in html, name in fields)

    def test_the_selected_email_provider_comes_first_and_the_others_are_not_in_use(self):
        content = self.client.get(self.url).content.decode()
        unused = content.index("Not in use (3)")

        self.assertLess(content.index('id="rate-card-ses_send"'), unused)
        for channel in (Channel.GRAPH_SEND, Channel.SMTP_SEND, Channel.GMAIL_API_SEND):
            self.assertGreater(content.index(f'id="rate-card-{channel}"'), unused)
        self.assertLess(content.index('id="rates-sms-heading"'), content.index('id="rate-card-sms_send"'))
        inbox = content.index('id="rates-inbox-heading"')
        self.assertGreater(content.index('id="rate-card-graph_read"'), inbox)
        self.assertGreater(content.index('id="rate-card-gmail_imap"'), inbox)

    def test_selecting_another_provider_moves_its_card_up(self):
        self.email_config.provider = "graph"
        self.email_config.save(update_fields=["provider"])

        content = self.client.get(self.url).content.decode()

        unused = content.index("Not in use (3)")
        self.assertLess(content.index('id="rate-card-graph_send"'), unused)
        self.assertGreater(content.index('id="rate-card-ses_send"'), unused)

    def test_cards_show_the_live_status_lines(self):
        self.state(Channel.SES_SEND, self.ses_identity, discovered_rate=14.0, discovered_at=READ_AT)

        html = self.card_html(self.client.get(self.url), Channel.SES_SEND)

        self.assertIn("Now: 12.6 recipients/sec · Smart · 90% of the 14 recipients/sec limit", html)
        self.assertIn("Provider limit: 14 recipients/sec (reported by AWS 5 min ago)", html)
        self.assertIn("AWS Region us-west-2 · in use", html)

    def test_the_gmail_api_card_says_its_limits_include_mail_sent_in_gmail(self):
        response = self.client.get(self.url)

        note = self.card(response, Channel.GMAIL_API_SEND).note
        self.assertTrue(note.startswith("Google's daily limits are per Google account"))
        self.assertIn(escape(note), self.card_html(response, Channel.GMAIL_API_SEND))
        self.assertNotIn("data-rate-note", self.card_html(response, Channel.SES_SEND))


class ManualRateTests(DeliveryRatesTestCase):
    def test_manual_rate_is_read_only_with_its_note_while_smart_rate_is_on(self):
        self.set_policy(Channel.GRAPH_SEND, smart_enabled=False)

        response = self.client.get(self.url)

        smart_card = self.card_html(response, Channel.SES_SEND)
        manual_card = self.card_html(response, Channel.GRAPH_SEND)
        self.assertRegex(smart_card, r'name="ses_send-manual_rate"[^>]*readonly')
        self.assertNotRegex(manual_card, r'name="graph_send-manual_rate"[^>]*readonly')
        self.assertIn(f"data-rate-manual-note>{MANUAL_RATE_NOTE}", smart_card)
        self.assertIn(f"data-rate-manual-note hidden>{MANUAL_RATE_NOTE}", manual_card)

    def test_a_manual_rate_posted_while_smart_rate_is_on_is_stored_and_kept_across_switches(self):
        self.client.post(self.url, self.post_data(**{"graph_send-manual_rate": "12.5"}))
        policy = self.policy(Channel.GRAPH_SEND)
        self.assertEqual((policy.smart_enabled, policy.manual_rate), (True, Decimal("12.5")))

        for smart in (None, "on", None):
            self.client.post(self.url, self.post_data(**{"graph_send-smart_enabled": smart}))
            self.assertEqual(self.policy(Channel.GRAPH_SEND).manual_rate, Decimal("12.5"))
        self.assertFalse(self.policy(Channel.GRAPH_SEND).smart_enabled)

    def test_stored_rates_are_shown_as_typed(self):
        response = self.client.get(self.url)

        self.assertRegex(self.card_html(response, Channel.GRAPH_SEND), r'name="graph_send-manual_rate"[^>]*value="24"')
