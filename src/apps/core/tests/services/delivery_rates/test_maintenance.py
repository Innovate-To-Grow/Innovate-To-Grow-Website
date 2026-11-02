"""The worker's delivery-rate upkeep: due limit reads (the identity in use first) and the purges."""

from datetime import timedelta
from unittest.mock import call, patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import DeliveryRateState, DeliveryUsageBucket
from apps.core.services.delivery_rates import families, maintenance

THIS = "apps.core.tests.services.delivery_rates.test_maintenance"


def active_ses():
    return "ses_send", "7:us-west-2"


def make_state(identity, *, idle_days=0, **values):
    state = DeliveryRateState.objects.create(
        channel="graph_send", identity=identity, cooldown_group=f"graph:{identity}", **values
    )
    DeliveryRateState.objects.filter(pk=state.pk).update(updated_at=timezone.now() - timedelta(days=idle_days))
    return state


class DeliveryRateMaintenanceTests(TestCase):
    @patch.dict(families._RESOLVERS, {"email": f"{THIS}.active_ses"})
    @patch.object(maintenance, "refresh_discovery", return_value=1)
    def test_due_limits_are_read_for_the_identity_in_use_then_the_rest(self, refresh):
        result = maintenance.run_maintenance()

        self.assertEqual(refresh.call_args_list[0], call("ses_send", "7:us-west-2"))
        self.assertCountEqual(refresh.call_args_list[1:], [call("ses_send"), call("sms_send")])
        self.assertEqual(result.limits_read, 3)

    def test_idle_identities_are_purged_unless_a_breaker_or_cooldown_is_active(self):
        now = timezone.now()
        idle = make_state("old@example.edu", idle_days=31)
        DeliveryUsageBucket.objects.create(state=idle, bucket_start=now - timedelta(days=31), total=3)
        make_state("recent@example.edu", idle_days=2)
        make_state("stopped@example.edu", idle_days=40, breaker_state=DeliveryRateState.BreakerState.OPEN)
        make_state("cooling@example.edu", idle_days=40, cooldown_until=now + timedelta(minutes=5))

        result = maintenance.run_maintenance()

        self.assertEqual(result.states_purged, 1)
        self.assertEqual(
            set(DeliveryRateState.objects.values_list("identity", flat=True)),
            {"recent@example.edu", "stopped@example.edu", "cooling@example.edu"},
        )
        self.assertFalse(DeliveryUsageBucket.objects.exists())

    def test_usage_buckets_past_their_retention_are_purged(self):
        state = make_state("i2g@example.edu")
        now = timezone.now()
        DeliveryUsageBucket.objects.create(state=state, bucket_start=now - timedelta(days=3), total=1)
        DeliveryUsageBucket.objects.create(state=state, bucket_start=now - timedelta(hours=1), total=1)

        self.assertEqual(maintenance.run_maintenance().buckets_purged, 1)
        self.assertEqual(DeliveryUsageBucket.objects.count(), 1)
