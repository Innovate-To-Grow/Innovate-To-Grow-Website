"""``inbox.health``: resetting account states and pruning those of accounts no longer read."""

from unittest.mock import patch

from django.db import DatabaseError

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.polling import health
from apps.mail.tests.services.inbox.health.state.helpers import (
    ACCOUNT,
    GRAPH,
    GRAPH_OTHER,
    LOGGER,
    HealthCase,
    Status,
    state,
)


class ResetAndPruneTests(HealthCase):
    def setUp(self):
        super().setUp()
        for account in (ACCOUNT, GRAPH, GRAPH_OTHER):
            state(account, status=Status.UNREACHABLE, detail="Could not connect", checked_at=self.now)

    def statuses(self):
        return dict(InboxAccountState.objects.values_list("account_key", "status"))

    def test_reset_by_key(self):
        health.reset([ACCOUNT.key])

        self.assertEqual(
            self.statuses(),
            {ACCOUNT.key: Status.UNKNOWN, GRAPH.key: Status.UNREACHABLE, GRAPH_OTHER.key: Status.UNREACHABLE},
        )
        self.assertEqual(InboxAccountState.objects.get(account_key=ACCOUNT.key).detail, "")
        self.assertEqual(health.hidden_keys([ACCOUNT, GRAPH]), {GRAPH.key})

    def test_reset_by_prefix(self):
        health.reset(prefix="graph:")

        self.assertEqual(
            self.statuses(),
            {ACCOUNT.key: Status.UNREACHABLE, GRAPH.key: Status.UNKNOWN, GRAPH_OTHER.key: Status.UNKNOWN},
        )

    def test_reset_everything(self):
        health.reset()

        self.assertEqual(set(self.statuses().values()), {Status.UNKNOWN})

    def test_reset_with_no_keys_resets_nothing(self):
        health.reset([])

        self.assertEqual(set(self.statuses().values()), {Status.UNREACHABLE})

    def test_reset_never_raises(self):
        with (
            patch.object(InboxAccountState.objects, "exclude", side_effect=DatabaseError("locked")),
            self.assertLogs(LOGGER, "ERROR"),
        ):
            health.reset()

    def test_prune_deletes_the_states_of_accounts_no_longer_read(self):
        self.assertEqual(health.prune([ACCOUNT]), 2)

        self.assertEqual(list(InboxAccountState.objects.values_list("account_key", flat=True)), [ACCOUNT.key])

    def test_with_no_account_every_state_is_pruned(self):
        self.assertEqual(health.prune([]), 3)
        self.assertFalse(InboxAccountState.objects.exists())
