"""The universal inbox reply views: a reply names the address it is sent From (``sender``)."""

from django.urls import reverse

from apps.mail.tests.admin.inbox.universal.helpers import (
    DEFAULT,
    GRAPH,
    IMAP_SENDER,
    UniversalInboxViewCase,
    detail,
)


class ReplySenderViewTests(UniversalInboxViewCase):
    def setUp(self):
        super().setUp()
        self.fetch = self.patch("fetch_inbox_message", return_value=detail())
        self.identities = self.patch("send_identities", return_value=[DEFAULT, IMAP_SENDER])
        self.send_reply = self.patch("send_reply", return_value="")

    def fragment_url(self, query="?account=imap:7"):
        return reverse("admin:mail_inbox_reply_fragment", args=["42"]) + query

    def test_the_form_starts_from_the_address_the_message_was_received_at(self):
        response = self.client.get(self.fragment_url())

        self.fetch.assert_called_once_with("42", account="imap:7")
        self.assertContains(response, 'name="sender"')
        self.assertContains(response, '<option value="imap:7" selected>i2g@gmail.com (SMTP · smtp.gmail.com)</option>')
        self.assertContains(response, "notify@ucmerced.edu (Notification Delivery · AWS SES)")
        self.assertNotContains(response, '<option value="default" selected>', html=False)
        self.assertContains(response, self.fragment_url().replace("imap:7", "imap%3A7"))

    def test_the_form_starts_from_notification_delivery_otherwise(self):
        self.fetch.return_value = detail(account=GRAPH)

        response = self.client.get(self.fragment_url("?account=graph:i2g@contoso.com"))

        self.assertContains(response, '<option value="default" selected>', html=False)

    def test_without_any_sender_the_form_shows_the_notification_address(self):
        self.identities.return_value = []

        response = self.client.get(self.fragment_url())

        self.assertNotContains(response, 'name="sender"')
        self.assertContains(response, "From:")

    def test_a_sender_listing_failure_is_logged_and_offers_no_choice(self):
        self.identities.side_effect = RuntimeError("boom")

        with self.assertLogs("apps.mail.admin.inbox", "ERROR"):
            response = self.client.get(self.fragment_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="sender"')

    def test_the_post_passes_the_sender_through(self):
        response = self.client.post(
            self.fragment_url(), {"reply_body": "Thanks", "to_email": "pat@example.com", "sender": "imap:7"}
        )

        self.assertEqual(response.json(), {"ok": True, "message": "Reply sent to pat@example.com."})
        self.fetch.assert_called_once_with("42", account="imap:7")
        self.assertEqual(self.send_reply.call_args.kwargs["sender"], "imap:7")

    def test_a_post_without_a_sender_uses_the_default(self):
        for data in ({}, {"sender": "  "}):
            with self.subTest(data=data):
                self.send_reply.reset_mock()

                self.client.post(self.fragment_url(), {"reply_body": "Thanks", **data})

                self.assertEqual(self.send_reply.call_args.kwargs["sender"], "default")

    def test_a_refused_sender_is_reported(self):
        self.send_reply.return_value = "That From address is not available."

        response = self.client.post(self.fragment_url(), {"reply_body": "Thanks", "sender": "imap:999"})

        self.assertEqual(response.json(), {"ok": False, "error": "That From address is not available."})

    def test_the_reply_page_offers_the_senders_and_posts_the_choice(self):
        url = reverse("admin:mail_inbox_reply", args=["42"]) + "?account=imap:7"

        page = self.client.get(url)
        sent = self.client.post(url, {"reply_body": "Thanks", "sender": "imap:7"})

        self.assertContains(page, 'id="reply-sender" name="sender"')
        self.assertContains(page, '<option value="imap:7" selected>', html=False)
        self.assertEqual(self.send_reply.call_args.kwargs["sender"], "imap:7")
        self.assertRedirects(
            sent, reverse("admin:mail_inbox_detail", args=["42"]) + "?account=imap%3A7", fetch_redirect_response=False
        )
