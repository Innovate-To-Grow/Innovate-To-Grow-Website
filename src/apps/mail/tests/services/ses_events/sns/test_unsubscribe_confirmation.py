from unittest.mock import patch

from django.test import TestCase

from apps.mail.services.email_monitoring.ses_events import process_sns_envelope


class UnsubscribeConfirmationTests(TestCase):
    def test_unsubscribe_confirmation_is_logged_and_noop(self):
        # Should not raise and not attempt any network call.
        process_sns_envelope({"Type": "UnsubscribeConfirmation", "TopicArn": "arn:x"})


class SubscriptionUrlopenFailureTests(TestCase):
    def test_failed_auto_confirm_is_swallowed(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription&Token=abc",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch(
            "apps.mail.services.email_monitoring.ses_events.subscription.fetch_sns_https",
            side_effect=RuntimeError("network down"),
        ) as mock_fetch:
            # Should not raise even though the confirmation request failed.
            process_sns_envelope(envelope)
            mock_fetch.assert_called_once()


class ParseTimestampTests(TestCase):
    def test_parse_ts_returns_none_for_empty(self):
        from apps.mail.services.email_monitoring.ses_events.handlers import parse_ts

        self.assertIsNone(parse_ts(""))

    def test_parse_ts_uses_fromisoformat_fallback(self):
        from apps.mail.services.email_monitoring.ses_events.handlers import parse_ts

        # Django's parse_datetime is permissive; force the fromisoformat fallback
        # by making parse_datetime return None for an otherwise-valid ISO value.
        with patch("apps.mail.services.email_monitoring.ses_events.handlers.parse_datetime", return_value=None):
            result = parse_ts("2026-04-22T12:00:00Z")

        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_parse_ts_returns_none_for_garbage(self):
        from apps.mail.services.email_monitoring.ses_events.handlers import parse_ts

        with patch("apps.mail.services.email_monitoring.ses_events.handlers.parse_datetime", return_value=None):
            self.assertIsNone(parse_ts("not-a-timestamp"))


class SubscriptionConfirmationTests(TestCase):
    def test_auto_confirm_calls_subscribe_url(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription&Token=abc",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch(
            "apps.mail.services.email_monitoring.ses_events.subscription.fetch_sns_https", return_value=b"<ok/>"
        ) as mock_fetch:
            process_sns_envelope(envelope)
            mock_fetch.assert_called_once()
            self.assertIn("ConfirmSubscription", mock_fetch.call_args.args[0])

    def test_non_amazonaws_subscribe_url_is_skipped(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://evil.example.com/trick",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("apps.mail.services.email_monitoring.ses_events.subscription.fetch_sns_https") as mock_fetch:
            process_sns_envelope(envelope)
            mock_fetch.assert_not_called()

    def test_amazonaws_lookalike_subscribe_url_is_skipped(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://sns.us-west-2.amazonaws.com.evil.example/?Action=ConfirmSubscription",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("apps.mail.services.email_monitoring.ses_events.subscription.fetch_sns_https") as mock_fetch:
            process_sns_envelope(envelope)
            mock_fetch.assert_not_called()

    def test_http_subscribe_url_is_skipped(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "http://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("apps.mail.services.email_monitoring.ses_events.subscription.fetch_sns_https") as mock_fetch:
            process_sns_envelope(envelope)
            mock_fetch.assert_not_called()

    def test_non_confirm_subscribe_url_action_is_skipped(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=GetTopicAttributes",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("apps.mail.services.email_monitoring.ses_events.subscription.fetch_sns_https") as mock_fetch:
            process_sns_envelope(envelope)
            mock_fetch.assert_not_called()
