import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.notifications import (
    send_subscription_confirmation,
    subscription_confirmation_dedupe_key,
)


class SubscriptionConfirmationEmailTests(APITestCase):
    """The best-effort confirmation helper and its outbox key."""

    @patch("apps.mail.services.tokens.notifications.email_api.send_notification_email")
    def test_confirmation_skipped_without_any_address(self, mock_send):
        member = Member.objects.create_user(password="x")  # no ContactEmail
        self.assertEqual(member.get_primary_email(), "")

        for action in ("unsubscribe", "resubscribe"):
            with self.subTest(action=action):
                send_subscription_confirmation(
                    member=member, action=action, email_ids=[str(uuid.uuid4())], changed_at=timezone.now()
                )

        mock_send.assert_not_called()

    def test_unknown_action_is_rejected(self):
        member = make_member(email="action@example.com")
        with self.assertRaises(ValueError):
            send_subscription_confirmation(member=member, action="delete", email_ids=["x"], changed_at=timezone.now())

    def test_dedupe_key_is_one_per_member_action_and_hour(self):
        member_id = uuid.uuid4()
        start = datetime(2026, 10, 1, 10, 0, 5, tzinfo=UTC)

        def key(action="unsubscribe", *, member=member_id, changed_at=start):
            return subscription_confirmation_dedupe_key(action, member_id=member, changed_at=changed_at)

        self.assertRegex(key(), r"^subscription-confirmation:unsubscribe:[0-9a-f]{64}$")
        self.assertEqual(key(), key(changed_at=start + timedelta(minutes=59)))
        self.assertNotEqual(key(), key(changed_at=start + timedelta(hours=1)))
        self.assertNotEqual(key(), key("resubscribe"))
        self.assertNotEqual(key(), key(member=uuid.uuid4()))

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_outbox_keeps_one_confirmation_per_window(self):
        member = make_member(email="window@example.com")
        email_ids = [str(ContactEmail.objects.get(member=member).pk)]
        start = datetime(2026, 10, 1, 10, 0, 5, tzinfo=UTC)

        for changed_at in (start, start + timedelta(minutes=30), start + timedelta(hours=1)):
            send_subscription_confirmation(
                member=member, action="unsubscribe", email_ids=email_ids, changed_at=changed_at
            )

        self.assertEqual(BackgroundJob.objects.filter(kind="authn.notification_email").count(), 2)

    @patch("apps.mail.services.tokens.notifications.start_in_process_task")
    def test_in_process_path_keeps_one_confirmation_per_window(self, start_task):
        cache.clear()  # also empties the throttle alias that holds the window marker
        member = make_member(email="window-local@example.com")
        email_ids = [str(ContactEmail.objects.get(member=member).pk)]

        for action in ("unsubscribe", "unsubscribe", "resubscribe", "resubscribe"):
            send_subscription_confirmation(member=member, action=action, email_ids=email_ids, changed_at=timezone.now())

        self.assertEqual(start_task.call_count, 2)
        self.assertEqual(
            [call.kwargs["name"] for call in start_task.call_args_list],
            [
                "subscription-confirmation-unsubscribe",
                "subscription-confirmation-resubscribe",
            ],
        )

    def test_dedupe_key_requires_a_known_action_and_time(self):
        with self.assertRaises(ValueError):
            subscription_confirmation_dedupe_key("unsubscribe", member_id=uuid.uuid4(), changed_at=None)
        with self.assertRaises(ValueError):
            subscription_confirmation_dedupe_key("other", member_id=uuid.uuid4(), changed_at=timezone.now())
