from decimal import Decimal

from apps.core.models import SMTPProviderConfig

from .delivery_rates_helpers import READ_AT, SMS_IDENTITY, Channel, DeliveryRatesTestCase


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
