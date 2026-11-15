"""Creating an invitation in the admin sends it after the admin's transaction commits; its message still shows
(a real commit is needed to see that, hence ``TransactionTestCase``)."""

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from apps.authn.models import AdminInvitation
from apps.event.tests.helpers import make_superuser


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class InvitationSentAfterCommitTests(TransactionTestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    @patch("apps.authn.services.email.send_admin_invitation_email")
    def test_the_invitation_is_sent_after_the_save_commits_and_the_message_is_shown(self, send):
        in_transaction = []
        send.side_effect = lambda **kwargs: in_transaction.append(connection.in_atomic_block)

        response = self.client.post(
            reverse("admin:authn_admininvitation_add"),
            {"email": "new@example.com", "role": AdminInvitation.Role.ADMIN, "message": "", "_save": "Save"},
        )

        self.assertEqual(in_transaction, [False])
        shown = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("Invitation created and sent for new@example.com.", shown)
