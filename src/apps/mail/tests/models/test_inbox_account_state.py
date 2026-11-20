from django.db import IntegrityError
from django.test import TestCase

from apps.mail.models import InboxAccountState


class InboxAccountStateModelTests(TestCase):
    def test_defaults_and_label(self):
        state = InboxAccountState.objects.create(account_key="imap:1", address="i2g@gmail.com")

        self.assertEqual(
            (state.status, state.consecutive_failures, state.unread_count, state.messages),
            (InboxAccountState.Status.UNKNOWN, 0, 0, []),
        )
        self.assertIsNone(state.snapshot_at)
        self.assertEqual(str(state), "i2g@gmail.com: Not checked yet")

    def test_without_an_address_the_key_names_it(self):
        state = InboxAccountState(account_key="graph:x@contoso.com", status=InboxAccountState.Status.UNREACHABLE)

        self.assertEqual(str(state), "graph:x@contoso.com: Could not connect")

    def test_one_state_per_account(self):
        InboxAccountState.objects.create(account_key="imap:1")

        with self.assertRaises(IntegrityError):
            InboxAccountState.objects.create(account_key="imap:1")
