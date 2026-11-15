"""Revoking personal SMS sign-in links under real concurrency on PostgreSQL: separate connections, real row locks.

- An issuer that read the switch as on stores its link after a concurrent switch-off has committed: that link never
  signs anyone in, not even once the switch is on again.
- An opener whose claim waits on the revocation's row lock loses once the revocation commits: nobody is signed in
  after the switch-off.

``test_link_revocation`` covers the same races with a fixed order in one connection.
"""

import threading
import time
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings

from apps.event.tests.helpers import make_member
from apps.mail.models import SmsConfig, SmsLinkToken
from apps.mail.services.sms import links

from .policy_helpers import add_phone, sms_settings

PHONE = "+12095550101"
WAIT_SECONDS = 10


def start_thread(target, errors: list) -> threading.Thread:
    def run():
        close_old_connections()
        try:
            target()
        except Exception as exc:  # pragma: no cover - surfaced by the test's errors assertion
            errors.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def some_backend_waits_on_a_lock() -> bool:
    """Whether another connection to the test database is waiting on a row lock, within ``WAIT_SECONDS``."""
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0]:
                return True
        threading.Event().wait(0.02)
    return False


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row-lock semantics")
@override_settings(FRONTEND_URL="https://i2g.example.edu")
class RevocationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        sms_settings(links_enabled=True, personal_links_enabled=True)
        self.member = make_member(email="ada@example.com")
        add_phone(self.member, "2095550101")

    def issue(self) -> str:
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, phone=PHONE, redirect_path="/subscribe", validity_days=3
        )
        return url.rsplit("/l/", 1)[1]

    def assert_signs_nobody_in(self, token):
        opened = links.open_link(token)
        self.assertEqual((opened.kind, opened.member), ("redirect", None))

    def test_a_link_stored_after_a_concurrent_switch_off_never_signs_in(self):
        state_read, switched_off = threading.Event(), threading.Event()
        issued, errors = [], []
        real_token = links._new_token

        def token_once_switched_off():
            state_read.set()  # The issuer has read the switch as on; the INSERT comes next.
            switched_off.wait(WAIT_SECONDS)
            return real_token()

        with patch.object(links, "_new_token", side_effect=token_once_switched_off):
            issuer = start_thread(lambda: issued.append(self.issue()), errors)
            try:
                self.assertTrue(state_read.wait(WAIT_SECONDS))
                sms_settings(personal_links_enabled=False)  # Its own connection: committed before the INSERT.
            finally:
                switched_off.set()
                issuer.join(WAIT_SECONDS)

        self.assertEqual(errors, [])
        row = SmsLinkToken.objects.get(token_hash=links.token_digest(issued[0]))
        self.assertIsNone(row.revoked_at)  # Stored after the sweep: only its epoch stops it.
        self.assertLess(row.epoch, SmsConfig.load().personal_links_epoch)
        self.assert_signs_nobody_in(issued[0])
        sms_settings(personal_links_enabled=True)
        self.assert_signs_nobody_in(issued[0])

    def test_an_open_waiting_on_the_revocation_signs_nobody_in(self):
        token = self.issue()
        swept, commit = threading.Event(), threading.Event()
        opened, errors = [], []

        def switch_off_and_hold():
            with transaction.atomic():
                config = SmsConfig.load()
                config.personal_links_enabled = False
                config.save()  # The sweep holds the link's row lock until this transaction commits.
                swept.set()
                commit.wait(WAIT_SECONDS)

        admin, opener = start_thread(switch_off_and_hold, errors), None
        try:
            self.assertTrue(swept.wait(WAIT_SECONDS))
            opener = start_thread(lambda: opened.append(links.open_link(token)), errors)
            # The opener still reads the switch as on and the link as live; its claim waits on the row lock.
            self.assertTrue(some_backend_waits_on_a_lock())
        finally:
            commit.set()
            admin.join(WAIT_SECONDS)
            if opener is not None:
                opener.join(WAIT_SECONDS)

        self.assertEqual(errors, [])
        self.assertEqual((opened[0].kind, opened[0].member, opened[0].reason), ("redirect", None, "revoked"))
        row = SmsLinkToken.objects.get()
        self.assertEqual((row.first_used_at, row.use_count), (None, 0))
        self.assertIsNotNone(row.revoked_at)
