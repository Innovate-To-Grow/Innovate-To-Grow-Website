"""The admin's save-and-send paths send after the admin's own transaction commits, and their messages still reach
the page (a real commit is needed to see that, hence ``TransactionTestCase``)."""

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.db import connection
from django.test import TransactionTestCase, override_settings

from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class TicketSaveAndSendAfterCommitTests(TransactionTestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        event = make_event()
        self.vip = make_ticket(event, name="VIP")
        self.registration = make_registration(make_member(email="guest@example.com"), event, make_ticket(event))

    @patch("apps.event.services.registration_sheet_sync.schedule_registration_sync")
    @patch("apps.event.services.ticket.mail.send_ticket_email")
    def test_the_ticket_is_sent_after_the_save_commits_and_the_message_is_shown(self, send, _sync):
        in_transaction = []
        send.side_effect = lambda registration: in_transaction.append(connection.in_atomic_block)

        response = self.client.post(
            f"/admin/event/eventregistration/{self.registration.pk}/change/",
            {"ticket": str(self.vip.pk), "_send_ticket_email": "1"},
        )

        self.assertEqual(in_transaction, [False])
        self.assertEqual(send.call_args.args[0].ticket_id, self.vip.pk)
        shown = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any(text.startswith("Sent ticket email to") for text in shown), shown)
