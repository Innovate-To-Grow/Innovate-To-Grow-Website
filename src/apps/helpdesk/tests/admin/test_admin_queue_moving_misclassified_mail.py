from django.test import override_settings
from django.urls import reverse

from apps.helpdesk.tests.admin.test_admin_queue import ACTION_SESSION_KEY, Status, _ActionCase


class ActionTests(_ActionCase):
    def test_moving_misclassified_mail_to_the_queue(self):
        response = self.act("move_to_queue", self.automated, follow=True)

        self.automated.refresh_from_db()
        self.assertEqual((self.automated.automated, self.automated.status), (False, Status.OPEN))
        self.assertContains(response, "1 ticket moved to the queue.")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_merging_needs_the_typed_word(self):
        response = self.act("merge_tickets", self.new, self.open)
        self.assertIn("confirm-action", response.url)
        confirm = reverse("admin:helpdesk_ticket_confirm_action")
        token = self.client.session[ACTION_SESSION_KEY]["token"]

        self.client.post(confirm, {"confirmation_word": "ticket", "token": token})
        self.new.refresh_from_db()
        self.assertEqual(self.new.status, Status.NEW)

        self.client.post(confirm, {"confirmation_word": "merge", "token": token})
        self.new.refresh_from_db()
        self.assertEqual((self.new.status, self.new.merged_into), (Status.MERGED, self.open))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_marking_spam_needs_the_typed_word(self):
        self.act("mark_spam", self.open)
        token = self.client.session[ACTION_SESSION_KEY]["token"]

        self.client.post(reverse("admin:helpdesk_ticket_confirm_action"), {"confirmation_word": "SPAM", "token": token})

        self.open.refresh_from_db()
        self.assertEqual(self.open.status, Status.SPAM)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_merging_needs_two_tickets(self):
        response = self.act("merge_tickets", self.open, follow=True)

        self.assertContains(response, "Select at least two tickets")
