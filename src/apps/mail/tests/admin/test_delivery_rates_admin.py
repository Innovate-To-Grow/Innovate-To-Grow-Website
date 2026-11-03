"""Mail → Delivery Rates: the seven channel cards, their fields, validation and the live status JSON."""

from decimal import Decimal

from django.utils.html import escape

from apps.core.models import SMTPProviderConfig
from apps.core.models.base.delivery_rates import MANUAL_RATE_HELP, SMART_RATE_HELP
from apps.event.tests.helpers import make_admin
from apps.mail.admin.settings.rates_forms import MANUAL_RATE_NOTE

from .delivery_rates_helpers import NOW, READ_AT, SMS_IDENTITY, Channel, DeliveryRatesTestCase

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
    def test_staff_without_the_mail_app_are_refused_everywhere(self):
        self.client.force_login(make_admin(apps=["event"], email="nomail@example.com"))
        before = self.policy(Channel.SMS_SEND).manual_rate

        for method, url, data in (
            ("get", self.url, None),
            ("post", self.url, self.post_data(**{"sms_send-manual_rate": "0.5"})),
            ("get", self.status_url, None),
            ("post", "/admin/mail/settings/rates/graph_send/reset/", None),
        ):
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, data or {}).status_code, 403)
        self.assertEqual(self.policy(Channel.SMS_SEND).manual_rate, before)

    def test_mail_staff_who_are_not_superusers_open_the_page(self):
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


class ValidationTests(DeliveryRatesTestCase):
    def test_a_manual_rate_above_the_provider_limit_is_refused_on_its_field(self):
        response = self.client.post(self.url, self.post_data(**{"graph_send-manual_rate": "31"}))

        self.assertEqual(response.status_code, 200)
        form = self.card(response, Channel.GRAPH_SEND).form
        self.assertEqual(
            form.errors["manual_rate"], ["It cannot be set above the provider limit of 30 messages/min (Advanced)."]
        )
        self.assertEqual(self.policy(Channel.GRAPH_SEND).manual_rate, Decimal("24"))
        # Left editable (and posted as typed) so it can be fixed while Smart rate is on.
        html = self.card_html(response, Channel.GRAPH_SEND)
        self.assertRegex(html, r'name="graph_send-manual_rate"(?![^>]*readonly)[^>]*value="31"')
        self.assertIn('data-has-errors="true"', html)

    def test_a_documented_limit_can_be_lowered_but_not_raised(self):
        response = self.client.post(
            self.url, self.post_data(**{"graph_send-provider_limit": "31", "gmail_api_send-daily_limit": "2500"})
        )

        card = self.card(response, Channel.GRAPH_SEND)
        self.assertEqual(
            card.form.errors["provider_limit"],
            ["The documented limit is 30 messages/min. It can be lowered here, not raised."],
        )
        self.assertTrue(card.advanced_open)
        self.assertEqual(self.policy(Channel.GMAIL_API_SEND).daily_limit, 3_000)  # nothing saved

        self.client.post(self.url, self.post_data(**{"gmail_api_send-daily_limit": "2500"}))

        self.assertEqual(self.policy(Channel.GMAIL_API_SEND).daily_limit, 2_500)

    def test_an_error_on_a_card_not_in_use_opens_it(self):
        response = self.client.post(self.url, self.post_data(**{"smtp_send-daily_message_limit": "abc"}))

        self.assertTrue(response.context["email_unused_open"])
        self.assertIn('<details class="i2g-rates-unused mt-4" open>', response.content.decode())

    def test_a_lower_limit_above_the_manual_rate_refuses_the_manual_rate(self):
        response = self.client.post(self.url, self.post_data(**{"sms_send-provider_limit": "0.5"}))

        self.assertIn("manual_rate", self.card(response, Channel.SMS_SEND).form.errors)

        self.client.post(self.url, self.post_data(**{"sms_send-provider_limit": "0.5", "sms_send-manual_rate": "0.5"}))

        policy = self.policy(Channel.SMS_SEND)
        self.assertEqual((policy.provider_limit, policy.manual_rate), (Decimal("0.5"), Decimal("0.5")))


class PlaceholderTests(DeliveryRatesTestCase):
    def placeholder(self, response, channel, field):
        html = self.card_html(response, channel)
        tag = html[html.index(f'name="{channel}-{field}"') :]
        tag = tag[: tag.index(">")]
        return tag.split('placeholder="', 1)[1].split('"', 1)[0] if 'placeholder="' in tag else None

    def test_blank_limits_show_what_applies_instead(self):
        self.set_policy(Channel.GRAPH_SEND, provider_limit=None, daily_limit=None)
        self.set_policy(Channel.GMAIL_API_SEND, provider_limit=None)

        response = self.client.get(self.url)

        self.assertEqual(self.placeholder(response, "graph_send", "provider_limit"), "30 messages/min documented")
        self.assertEqual(self.placeholder(response, "graph_send", "daily_limit"), "10,000 per 24 h documented")
        self.assertEqual(
            self.placeholder(response, "gmail_imap", "provider_limit"),
            "Unknown: Smart rate uses the 30 sessions/min app default",
        )
        self.assertEqual(self.placeholder(response, "graph_send", "transactional_reserve"), "0.1 (the default)")
        self.assertEqual(
            self.placeholder(response, "gmail_api_send", "internal_domain"), "Blank: every recipient counts as external"
        )
        self.assertEqual(self.placeholder(response, "ses_send", "daily_limit"), "Not read yet: AWS reports it")
        self.assertEqual(self.placeholder(response, "sms_send", "daily_limit"), "None documented")

    def test_reported_limits_name_the_provider_and_when_it_reported_them(self):
        self.state(
            Channel.SES_SEND,
            self.ses_identity,
            discovered_rate=14.0,
            discovered_daily=50_000,
            discovered_at=READ_AT,
            discovered_extra={"max_24_hour_send": 50_000.0},
        )
        self.state(
            Channel.SMS_SEND,
            SMS_IDENTITY,
            discovered_parts_rate=3.0,
            discovered_at=READ_AT,
            discovered_extra={"number_type": "TOLL_FREE"},
        )

        response = self.client.get(self.url)

        self.assertEqual(
            self.placeholder(response, "ses_send", "provider_limit"), "AWS reports 14 recipients/sec (13:05 UTC)"
        )
        self.assertEqual(self.placeholder(response, "ses_send", "daily_limit"), "AWS reports 50,000 per 24 h")
        self.assertEqual(
            self.placeholder(response, "sms_send", "parts_limit"), "AWS SMS reports 3 MPS (TOLL_FREE, 13:05 UTC)"
        )

    def test_the_smtp_host_in_use_shows_its_documented_daily_limit(self):
        SMTPProviderConfig.objects.create(
            name="Gmail SMTP",
            is_active=True,
            host="smtp.gmail.com",
            port=587,
            username="i2g@example.com",
            password="app-password",
            use_tls=True,
        )
        self.email_config.provider = "smtp"
        self.email_config.save(update_fields=["provider"])

        response = self.client.get(self.url)

        self.assertEqual(
            self.placeholder(response, "smtp_send", "daily_message_limit"),
            "2,000 per 24 h documented for smtp.gmail.com",
        )

    def test_documented_ceilings_are_in_the_help_text(self):
        html = self.card_html(self.client.get(self.url), Channel.GMAIL_API_SEND)

        self.assertIn("At most 60 messages / minute (documented): it can be lowered here, not raised.", html)
        self.assertIn("At most 2,000 external recipients / 24 h (documented)", html)


class ReportedTests(DeliveryRatesTestCase):
    def test_the_last_provider_report_is_listed_read_only(self):
        self.state(
            Channel.SES_SEND,
            self.ses_identity,
            discovered_rate=14.0,
            discovered_daily=50_000,
            discovered_used_24h=1_240,
            discovered_at=READ_AT,
            discovered_extra={
                "max_24_hour_send": 50_000.0,
                "sending_enabled": True,
                "enforcement_status": "HEALTHY",
                "production_access": True,
                "api": "sesv2",
            },
        )
        self.state(
            Channel.SMS_SEND,
            SMS_IDENTITY,
            discovered_parts_rate=3.0,
            discovered_at=READ_AT,
            discovered_extra={"number_type": "TOLL_FREE", "daily_message_caps": {}, "spend_limit": 1, "spend_max": 10},
        )

        response = self.client.get(self.url)

        self.assertEqual(
            self.card(response, Channel.SES_SEND).reported,
            (
                "Read 5 min ago (13:05 UTC) through sesv2",
                "MaxSendRate: 14 recipients/sec",
                "Max24HourSend: 50,000",
                "SentLast24Hours: 1,240",
                "EnforcementStatus: HEALTHY",
                "Sending enabled: yes",
                "Production access: yes",
            ),
        )
        self.assertEqual(
            self.card(response, Channel.SMS_SEND).reported,
            (
                "Read 5 min ago (13:05 UTC)",
                "NumberType: TOLL_FREE",
                "RateLimits (SMS): 3 parts/sec",
                "Text spend limit: USD 1 (maximum USD 10)",
            ),
        )
        self.assertIn("Reported by provider", self.card_html(response, Channel.SES_SEND))
        self.assertNotIn("Reported by provider", self.card_html(response, Channel.GRAPH_SEND))


class StatusJsonTests(DeliveryRatesTestCase):
    def test_the_status_json_has_every_channel_and_its_lines(self):
        self.state(Channel.SMS_SEND, SMS_IDENTITY, cooldown_until=NOW.replace(minute=15), cooldown_reason="throttled")

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        channels = {item["channel"]: item for item in response.json()["channels"]}
        self.assertEqual(list(channels), list(Channel.values))
        sms = channels["sms_send"]
        self.assertTrue(sms["held"])
        self.assertEqual(sms["identities"][0]["label"], "+12065550000 (us-west-2)")
        self.assertTrue(sms["identities"][0]["in_use"])
        self.assertEqual(sms["identities"][0]["lines"][0], "Paused until 13:15:00 UTC: AWS SMS asked to slow down")
        self.assertFalse(channels["graph_send"]["held"])
        self.assertTrue(channels["graph_send"]["identities"][0]["lines"][0].startswith("Now: "))

    def test_the_status_json_is_read_only(self):
        self.assertEqual(self.client.post(self.status_url).status_code, 405)
