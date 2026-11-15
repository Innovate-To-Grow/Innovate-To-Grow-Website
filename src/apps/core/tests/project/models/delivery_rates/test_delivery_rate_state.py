"""DeliveryRateState and DeliveryUsageBucket keys, and the background-job priority with its claim index."""

from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob, DeliveryRatePolicy, DeliveryRateState, DeliveryUsageBucket
from apps.core.models.records.background_job import DEFAULT_JOB_PRIORITY

Channel = DeliveryRatePolicy.Channel


def make_state(channel=Channel.GRAPH_SEND, identity="i2g@example.edu", **fields):
    return DeliveryRateState.objects.create(
        channel=channel, identity=identity, cooldown_group=f"graph:{identity}", **fields
    )


class DeliveryRateStateTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_new_identity_starts_closed_at_full_speed(self):
        state = make_state()
        state.refresh_from_db()

        self.assertEqual(state.breaker_state, DeliveryRateState.BreakerState.CLOSED)
        self.assertEqual((state.mode, state.breaker_scope, state.cooldown_reason), ("", "", ""))
        self.assertEqual((state.factor_base, state.consecutive_throttles), (1.0, 0))
        self.assertEqual(state.discovered_extra, {})
        self.assertIsNone(state.tat)
        self.assertEqual(str(state), "graph_send:i2g@example.edu")

    def test_one_row_per_channel_and_identity(self):
        make_state()
        make_state(channel=Channel.GRAPH_READ)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_state()
        self.assertEqual(DeliveryRateState.objects.filter(identity="i2g@example.edu").count(), 2)

    def test_usage_buckets_are_unique_per_state_and_start_and_go_with_the_state(self):
        state = make_state()
        start = timezone.now().replace(microsecond=0)
        bucket = DeliveryUsageBucket.objects.create(state=state, bucket_start=start, total=3, external=1, messages=2)
        DeliveryUsageBucket.objects.create(state=state, bucket_start=start + timedelta(minutes=5))
        self.assertEqual((bucket.bulk, bucket.total), (0, 3))
        self.assertIn(": 3", str(bucket))
        with self.assertRaises(IntegrityError), transaction.atomic():
            DeliveryUsageBucket.objects.create(state=state, bucket_start=start)

        state.delete()
        self.assertFalse(DeliveryUsageBucket.objects.exists())


class BackgroundJobPriorityTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_jobs_default_to_the_middle_priority_in_python_and_in_the_database(self):
        self.assertEqual(DEFAULT_JOB_PRIORITY, 50)
        job = BackgroundJob.objects.create(kind="test.kind", dedupe_key="python")
        self.assertEqual(job.priority, DEFAULT_JOB_PRIORITY)

        # An INSERT without the column (an older task during a rolling deploy) gets it from the database default.
        raw = BackgroundJob(kind="test.kind", dedupe_key="database")
        fields = [field for field in BackgroundJob._meta.concrete_fields if field.name != "priority"]
        columns = ", ".join(connection.ops.quote_name(field.column) for field in fields)
        values = [field.get_db_prep_save(field.pre_save(raw, add=True), connection) for field in fields]
        placeholders = ", ".join(["%s"] * len(fields))
        table = connection.ops.quote_name(BackgroundJob._meta.db_table)
        # Table and column names come from the model, every value is a parameter.
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"  # nosec B608
        with connection.cursor() as cursor:
            cursor.execute(sql, values)
        self.assertEqual(BackgroundJob.objects.get(pk=raw.pk).priority, DEFAULT_JOB_PRIORITY)

    def test_the_claim_index_leads_with_status_then_priority(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, BackgroundJob._meta.db_table)

        self.assertNotIn("core_job_claim_idx", constraints)
        claim = constraints["core_job_claim_priority_idx"]
        self.assertTrue(claim["index"])
        self.assertEqual(claim["columns"], ["status", "priority", "available_at", "created_at"])
