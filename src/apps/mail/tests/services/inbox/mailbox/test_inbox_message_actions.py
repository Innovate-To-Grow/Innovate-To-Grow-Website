from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.email import PermanentEmailDeliveryError
from apps.mail.services.inbox.connection import (
    INBOX_LIST_CACHE_KEY,
    InboxError,
)
from apps.mail.services.inbox.messages import (
    fetch_inbox_message,
    update_list_cache_seen,
)
from apps.mail.services.inbox.reply import (
    REPLY_SEND_FAILURE_MESSAGE,
    _build_reply_message,
    render_reply_html,
    send_reply,
)
from apps.mail.tests.services.inbox.mailbox.test_inbox_services import _fake_message, _inbox_context


class FetchInboxMessageTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_fetch_returns_cached_when_present(self):
        cache.set("inbox:msg:INBOX:42", {"uid": "42", "subject": "cached"}, 1800)
        self.assertEqual(fetch_inbox_message("42")["subject"], "cached")

    def test_fetch_cache_isolated_per_folder(self):
        cache.set("inbox:msg:INBOX:42", {"uid": "42", "subject": "inbox-msg"}, 1800)
        cache.set("inbox:msg:SENT:42", {"uid": "42", "subject": "sent-msg"}, 1800)

        self.assertEqual(fetch_inbox_message("42")["subject"], "inbox-msg")
        self.assertEqual(fetch_inbox_message("42", folder="SENT")["subject"], "sent-msg")

    def test_fetch_returns_detailed_message_and_caches(self):
        client = Mock()
        client.fetch.return_value = [_fake_message()]

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            result = fetch_inbox_message("42")

        self.assertEqual(result["uid"], "42")
        self.assertEqual(cache.get("inbox:msg:INBOX:42"), result)

    def test_fetch_raises_when_message_not_found(self):
        client = Mock()
        client.fetch.return_value = []

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            with self.assertRaisesMessage(InboxError, "Message not found."):
                fetch_inbox_message("999")

    def test_fetch_wraps_unexpected_error(self):
        with patch("apps.mail.services.inbox._open_inbox", side_effect=RuntimeError("boom")):
            with self.assertRaisesMessage(InboxError, "Failed to fetch the message."):
                fetch_inbox_message("42")


class UpdateListCacheSeenTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_marks_matching_uid_seen(self):
        cache.set(f"{INBOX_LIST_CACHE_KEY}:INBOX:30", [{"uid": "42", "is_seen": False}], 300)

        update_list_cache_seen("42")

        updated = cache.get(f"{INBOX_LIST_CACHE_KEY}:INBOX:30")
        self.assertTrue(updated[0]["is_seen"])

    def test_skips_when_no_cache_for_limit(self):
        # No cache set; should not raise.
        update_list_cache_seen("42")
        self.assertIsNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:INBOX:30"))

    def test_update_scoped_to_folder(self):
        cache.set(f"{INBOX_LIST_CACHE_KEY}:INBOX:30", [{"uid": "42", "is_seen": False}], 300)
        cache.set(f"{INBOX_LIST_CACHE_KEY}:SENT:30", [{"uid": "42", "is_seen": False}], 300)

        update_list_cache_seen("42", folder="INBOX")

        self.assertTrue(cache.get(f"{INBOX_LIST_CACHE_KEY}:INBOX:30")[0]["is_seen"])
        # The SENT list with the same uid must be untouched (uids are folder-scoped).
        self.assertFalse(cache.get(f"{INBOX_LIST_CACHE_KEY}:SENT:30")[0]["is_seen"])


class ReplyRenderTests(TestCase):
    def test_render_reply_html_linkifies_urls(self):
        html = render_reply_html("Visit https://example.com now", quoted_text="prior text")
        self.assertIn('<a href="https://example.com"', html)
        self.assertIn("prior text", html)

    def test_build_reply_message_sets_threading_headers(self):
        config = SimpleNamespace(source_address="I2G <reply@example.com>")
        message = _build_reply_message(
            config=config,
            to_email="alice@example.com",
            subject="Re: Hi",
            html="<p>Hi</p>",
            cc_list=["cc@example.com"],
            in_reply_to="<orig@example.com>",
            references="<a@example.com> <b@example.com>",
        )

        self.assertEqual(message.headers["In-Reply-To"], "<orig@example.com>")
        self.assertEqual(message.headers["References"], "<a@example.com> <b@example.com>")
        self.assertEqual(message.cc, ("cc@example.com",))


class SendReplyTests(TestCase):
    def setUp(self):
        self.email_config = EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            from_email="reply@example.com",
            from_name="I2G",
        )

    def test_send_reply_returns_empty_on_success(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch("apps.mail.services.inbox.reply.deliver_email") as mock_deliver:
            error = send_reply(
                to_email="alice@example.com",
                subject="Re: Hi",
                reply_body="Hello",
                cc_email="cc@example.com",
            )

        self.assertEqual(error, "")
        mock_deliver.assert_called_once()
        message = mock_deliver.call_args.args[0]
        self.assertEqual(message.envelope_recipients, ("alice@example.com", "cc@example.com"))

    def test_send_reply_returns_message_when_aws_credentials_missing(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch("apps.mail.services.inbox.reply.deliver_email", side_effect=PermanentEmailDeliveryError("missing")):
            error = send_reply(to_email="alice@example.com", subject="Re: Hi", reply_body="Hi")

        self.assertEqual(error, REPLY_SEND_FAILURE_MESSAGE)

    def test_send_reply_returns_failure_message_on_unexpected_error(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch(
            "apps.mail.services.inbox.reply.deliver_email",
            side_effect=PermanentEmailDeliveryError("provider down"),
        ):
            error = send_reply(to_email="alice@example.com", subject="Re: Hi", reply_body="Hi")

        self.assertEqual(error, REPLY_SEND_FAILURE_MESSAGE)
