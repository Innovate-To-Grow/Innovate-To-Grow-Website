from .delivery_rates_helpers import NOW, READ_AT, SMS_IDENTITY, Channel, DeliveryRatesTestCase


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
