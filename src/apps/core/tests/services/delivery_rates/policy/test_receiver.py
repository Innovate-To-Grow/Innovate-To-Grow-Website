from datetime import timedelta

from django.core.cache import cache
from django.db.models.signals import post_save
from django.test import TestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.delivery_rates.lifecycle import receivers
from apps.core.tests.services.delivery_rates.policy.test_snapshot import MAILBOX, SES, state

from ..helpers import START, Channel, FakeClock


class ReceiverTests(TestCase):
    def setUp(self):
        cache.clear()
        FakeClock().install(self)

    def test_every_config_model_is_connected(self):
        for label in receivers.CONFIG_CHANNELS:
            with self.subTest(label=label):
                from django.apps import apps

                self.assertTrue(post_save.has_listeners(apps.get_model(label)))

    def test_a_graph_config_save_half_opens_graph_permission_breakers_only(self):
        stopped = {
            "breaker_state": "open",
            "breaker_scope": "all",
            "breaker_reason": "permission",
            "breaker_retry_at": START + timedelta(hours=1),
        }
        send = state(Channel.GRAPH_SEND, MAILBOX, **stopped)
        read = state(Channel.GRAPH_READ, MAILBOX, **stopped)
        ses = state(Channel.SES_SEND, SES, **stopped)

        with self.captureOnCommitCallbacks(execute=True):
            receivers._saved(MicrosoftGraphProviderConfig, None)

        for row, retry in ((send, START), (read, START), (ses, START + timedelta(hours=1))):
            row.refresh_from_db()
            self.assertEqual(row.breaker_retry_at, retry)

    def test_fixture_loading_is_ignored(self):
        with self.captureOnCommitCallbacks() as callbacks:
            receivers._saved(MicrosoftGraphProviderConfig, None, raw=True)

        self.assertEqual(callbacks, [])

    def test_a_later_config_model_can_register_its_channels(self):
        self.addCleanup(receivers.CONFIG_CHANNELS.pop, "core.LegacyAccessGrant", None)

        receivers.register_config_channels("core.LegacyAccessGrant", [Channel.GMAIL_API_SEND])

        self.assertEqual(receivers.CONFIG_CHANNELS["core.LegacyAccessGrant"], (Channel.GMAIL_API_SEND,))
