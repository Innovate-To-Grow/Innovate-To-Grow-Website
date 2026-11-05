"""Mail → Delivery Rates: the saved history, the card actions (POST only) and the links from the other delivery
pages, whose old rate fields are gone."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.core.models import DeliveryRatePolicy, DeliveryRateState
from apps.mail.services.campaign.pacing import email_send_rate_line

from .delivery_rates_helpers import NOW, SMS_IDENTITY, Channel, DeliveryRatesTestCase

REFRESH = "apps.mail.admin.settings.rates.refresh_discovery"


def history():
    content_type = ContentType.objects.get_for_model(DeliveryRatePolicy)
    return list(LogEntry.objects.filter(content_type=content_type).order_by("action_time"))


class HistoryTests(DeliveryRatesTestCase):
    def test_a_save_records_each_changed_channel_with_old_and_new_values(self):
        data = self.post_data(
            **{
                "sms_send-smart_enabled": None,
                "sms_send-manual_rate": "0.5",
                "graph_send-daily_limit": "9000",
                "graph_send-limits_confirmed": "on",
            }
        )

        response = self.client.post(self.url, data)

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        messages = {entry.object_id: entry for entry in history()}
        sms, graph = self.policy(Channel.SMS_SEND), self.policy(Channel.GRAPH_SEND)
        self.assertEqual(set(messages), {str(sms.pk), str(graph.pk)})
        self.assertEqual(messages[str(sms.pk)].change_message, "sms_send: Smart rate on→off; manual 1→0.5")
        # The Graph policy's ceilings start blank since migration 0043 (the Graph configuration's limits apply).
        self.assertEqual(
            messages[str(graph.pk)].change_message,
            "graph_send: daily limit blank→9,000; tenant limits confirmed off→on",
        )
        for entry in messages.values():
            self.assertEqual((entry.user_id, entry.action_flag), (self.staff.pk, CHANGE))

    def test_an_unchanged_save_and_a_refused_one_leave_no_history(self):
        response = self.client.post(self.url, self.post_data(), follow=True)

        self.assertContains(response, "No delivery rates changed.")
        self.client.post(self.url, self.post_data(**{"graph_send-manual_rate": "31", "sms_send-manual_rate": "0.5"}))

        self.assertEqual(history(), [])
        self.assertEqual(str(self.policy(Channel.SMS_SEND).manual_rate), "1.000")


class ActionTests(DeliveryRatesTestCase):
    def action_url(self, channel, action):
        return reverse("admin:mail_delivery_rates_action", args=[channel, action])

    def test_actions_are_post_only(self):
        for action in ("check", "reset", "resume"):
            with self.subTest(action=action):
                self.assertEqual(self.client.get(self.action_url("ses_send", action)).status_code, 405)
        self.assertEqual(history(), [])

    def test_unknown_channels_and_actions_and_a_check_without_discovery_are_not_found(self):
        with patch(REFRESH) as refresh:
            for channel, action in (("fax_send", "reset"), ("ses_send", "delete"), ("graph_send", "check")):
                with self.subTest(channel=channel, action=action):
                    self.assertEqual(self.client.post(self.action_url(channel, action)).status_code, 404)
        refresh.assert_not_called()
        self.assertEqual(history(), [])

    def test_check_provider_limits_now_reads_the_identity_in_use(self):
        with patch(REFRESH, return_value=1) as refresh:
            ses = self.client.post(self.action_url("ses_send", "check"))
            self.client.post(self.action_url("sms_send", "check"))

        self.assertRedirects(ses, f"{self.url}#rate-card-ses_send", fetch_redirect_response=False)
        self.assertEqual(
            [call.args + (call.kwargs,) for call in refresh.call_args_list],
            [("ses_send", self.ses_identity, {"force": True}), ("sms_send", SMS_IDENTITY, {"force": True})],
        )
        self.assertEqual(
            [entry.change_message for entry in history()],
            ["ses_send: Check provider limits now", "sms_send: Check provider limits now"],
        )

    def test_check_provider_limits_now_without_an_account_says_so(self):
        self.aws_config.access_key_id = ""
        self.aws_config.secret_access_key = ""
        self.aws_config.save()

        with patch(REFRESH, return_value=0) as refresh:
            response = self.client.post(self.action_url("ses_send", "check"), follow=True)

        refresh.assert_called_once_with("ses_send", None, force=True)
        self.assertContains(response, "Nothing to read yet")

    def test_reset_smart_rate_starts_smart_rate_afresh_and_keeps_the_pause(self):
        until = NOW + timedelta(minutes=5)
        state = self.state(
            Channel.GRAPH_SEND, "mailer@example.com", mode="smart", last_cut_at=NOW, cooldown_until=until
        )

        self.client.post(self.action_url("graph_send", "reset"))

        state.refresh_from_db()
        self.assertEqual((state.mode, state.last_cut_at, state.cooldown_until), ("", None, until))
        self.assertEqual([entry.change_message for entry in history()], ["graph_send: Reset Smart rate"])

    def test_resume_sending_is_offered_only_while_held_and_clears_the_stop(self):
        self.assertIn('data-rate-action="resume" hidden', self.card_html(self.client.get(self.url), "ses_send"))
        state = self.state(
            Channel.SES_SEND,
            self.ses_identity,
            breaker_state=DeliveryRateState.BreakerState.OPEN,
            breaker_scope=DeliveryRateState.BreakerScope.ALL,
            breaker_reason="account_paused",
            breaker_retry_at=NOW + timedelta(minutes=15),
        )
        html = self.card_html(self.client.get(self.url), "ses_send")
        self.assertIn("Stopped: AWS reports sending is paused for this account", html)
        self.assertRegex(html, r'data-rate-action="resume"\s*class=')

        self.client.post(self.action_url("ses_send", "resume"))

        state.refresh_from_db()
        self.assertEqual(state.breaker_state, DeliveryRateState.BreakerState.CLOSED)
        self.assertEqual([entry.change_message for entry in history()], ["ses_send: Resume sending"])
        self.assertIn('data-rate-action="resume" hidden', self.card_html(self.client.get(self.url), "ses_send"))

    def test_each_button_posts_its_own_form_with_a_csrf_token(self):
        content = self.client.get(self.url).content.decode()

        for channel, action in (("ses_send", "check"), ("sms_send", "check"), ("graph_read", "reset")):
            form_id = f"rate-action-{channel}-{action}"
            self.assertIn(f'form="{form_id}"', content)
            start = content.index(f'<form id="{form_id}" method="post" action="{self.action_url(channel, action)}"')
            self.assertIn("csrfmiddlewaretoken", content[start : content.index("</form>", start)])
        self.assertNotIn("rate-action-graph_send-check", content)


class OtherPagesTests(DeliveryRatesTestCase):
    def test_notification_delivery_shows_both_send_rates_with_a_link(self):
        response = self.client.get(reverse("admin:mail_settings"))

        self.assertContains(response, "Send Rate", count=2)
        self.assertContains(response, 'href="/admin/mail/settings/rates/#rate-card-ses_send"')
        self.assertContains(response, 'href="/admin/mail/settings/rates/#rate-card-sms_send"')
        self.assertIn("messages/sec · Smart", response.context["sms_send_rate"])
        self.assertIn("recipients/sec · Smart", response.context["email_send_rate"])

    def test_the_old_rate_fields_and_texts_are_gone(self):
        for url in (reverse("admin:mail_settings"), reverse("admin:mail_settings_edit")):
            with self.subTest(url=url):
                response = self.client.get(url)
                for text in ("max_send_rate", "messages_per_minute", "about 30", "Campaign Send Rate"):
                    self.assertNotContains(response, text)
        edit = self.client.get(reverse("admin:mail_settings_edit"))
        self.assertContains(edit, 'href="/admin/mail/settings/rates/#rate-card-graph_send"')
        self.assertContains(edit, 'href="/admin/mail/settings/rates/#rate-card-gmail_api_send"')

    def test_the_delivery_dashboard_shows_the_send_rate_with_a_link(self):
        line = email_send_rate_line()
        with patch(
            "apps.mail.admin.delivery_dashboard.get_delivery_dashboard_data",
            return_value={"aws": {"send_rate": line}},
        ):
            response = self.client.get(reverse("admin:mail_delivery_dashboard"))

        self.assertIn("recipients/sec · Smart", line)
        self.assertContains(response, f"<span data-delivery-send-rate>{line}</span>")
        self.assertContains(response, 'href="/admin/mail/settings/rates/"')
