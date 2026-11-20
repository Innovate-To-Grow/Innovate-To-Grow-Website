"""The sidebar badge of Mail -> Inbox: the poller's unread count, for staff who may open the inbox only."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.admin.inbox.badge import inbox_unread_badge
from apps.mail.models import InboxAccountState
from apps.mail.tests.services.inbox.accounts.helpers import UniversalInboxMixin, gmail_account

UNREAD_TOTAL = "apps.mail.services.inbox.health.unread_total"


class InboxUnreadBadgeTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.gmail = gmail_account()
        self.state = InboxAccountState.objects.create(
            account_key=f"imap:{self.gmail.pk}",
            address=self.gmail.gmail_username,
            status=InboxAccountState.Status.OK,
            snapshot_at=timezone.now(),
            unread_count=7,
        )
        self.mail_staff = make_admin(apps=["mail"], email="mail@example.com")

    def badge(self, user):
        request = RequestFactory().get("/admin/")
        request.user = user
        return inbox_unread_badge(request)

    def set_unread(self, count):
        InboxAccountState.objects.filter(pk=self.state.pk).update(unread_count=count)
        cache.clear()

    def test_mail_staff_see_the_unread_count(self):
        self.assertEqual(self.badge(self.mail_staff), "7")
        self.assertEqual(self.badge(make_superuser()), "7")

    def test_anyone_else_sees_nothing(self):
        other_staff = make_admin(apps=["event"], email="event@example.com")

        for user in (other_staff, AnonymousUser()):
            with self.subTest(user=user), patch(UNREAD_TOTAL) as unread_total:
                self.assertEqual(self.badge(user), "")
                unread_total.assert_not_called()

    def test_a_request_without_a_user_sees_nothing(self):
        self.assertEqual(inbox_unread_badge(SimpleNamespace()), "")

    def test_no_unread_mail_shows_no_badge(self):
        self.set_unread(0)

        self.assertEqual(self.badge(self.mail_staff), "")

    def test_more_than_99_is_capped(self):
        for count, shown in ((99, "99"), (100, "99+"), (2500, "99+")):
            with self.subTest(count=count):
                self.set_unread(count)

                self.assertEqual(self.badge(self.mail_staff), shown)

    def test_a_counting_failure_shows_no_badge(self):
        with (
            patch(UNREAD_TOTAL, side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.admin.inbox.badge", "ERROR"),
        ):
            self.assertEqual(self.badge(self.mail_staff), "")
