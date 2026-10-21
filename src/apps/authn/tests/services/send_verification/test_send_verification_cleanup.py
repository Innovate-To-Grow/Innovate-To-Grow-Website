"""Batched retention cleanup for send-verification rows and expired sessions."""

import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import connection, models
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest
from apps.authn.services.send_verification import cleanup_expired_records, clear_expired_sessions

RETENTION = timedelta(days=14)  # the default ``retention_days``


class CleanupTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.old = self.now - RETENTION - timedelta(days=1)  # past the retention window
        self.recent = self.now - timedelta(days=1)  # expired, but still retained

    def make_challenges(self, count, *, expires_at, status=SendVerificationChallenge.Status.CONSUMED):
        return SendVerificationChallenge.objects.bulk_create(
            SendVerificationChallenge(
                operation="login.request_code",
                destination_kind="email",
                destination_normalized=f"user{index}@example.com",
                principal_type="session",
                algorithm="PBKDF2/SHA-256",
                cost=10,
                expires_at=expires_at,
                status=status,
            )
            for index in range(count)
        )

    def make_requests(self, count=None, *, idempotency_expires_at, challenges=None):
        challenges = list(challenges) if challenges is not None else [None] * count
        return SendVerificationRequest.objects.bulk_create(
            SendVerificationRequest(
                request_id=uuid.uuid4(),
                challenge=challenge,
                operation="login.request_code",
                channel="email",
                destination_kind="email",
                destination_normalized="user@example.com",
                principal_type="session",
                request_fingerprint="f" * 64,
                idempotency_expires_at=idempotency_expires_at,
            )
            for challenge in challenges
        )

    def cleanup(self, batch_size):
        return cleanup_expired_records(now=self.now, batch_size=batch_size)


class BatchedCleanupTests(CleanupTestCase):
    def test_every_expired_row_is_deleted_and_no_retained_row(self):
        old = self.make_challenges(23, expires_at=self.old)
        retained = self.make_challenges(4, expires_at=self.recent)
        live = self.make_challenges(3, expires_at=self.now + timedelta(minutes=5), status="pending")
        # Requests that outlive their (deleted) challenge keep existing with the reference cleared.
        kept_requests = self.make_requests(idempotency_expires_at=self.now + timedelta(hours=1), challenges=old[:12])
        old_requests = self.make_requests(idempotency_expires_at=self.old, challenges=old[12:])
        old_unlinked = self.make_requests(7, idempotency_expires_at=self.old)
        retained_requests = self.make_requests(2, idempotency_expires_at=self.recent)

        result = self.cleanup(batch_size=5)

        self.assertEqual(result, {"expired_challenges": 0, "deleted_challenges": 23, "deleted_requests": 18})
        self.assertEqual(
            set(SendVerificationChallenge.objects.values_list("pk", flat=True)),
            {row.pk for row in retained + live},
        )
        self.assertEqual(
            set(SendVerificationRequest.objects.values_list("pk", flat=True)),
            {row.pk for row in kept_requests + retained_requests},
        )
        self.assertFalse(SendVerificationRequest.objects.filter(challenge__isnull=False).exists())
        self.assertEqual(len(old_requests) + len(old_unlinked), 18)

    def test_overdue_pending_challenges_are_expired_in_batches(self):
        overdue = self.make_challenges(12, expires_at=self.now - timedelta(seconds=1), status="pending")
        live = self.make_challenges(2, expires_at=self.now + timedelta(minutes=5), status="pending")

        result = self.cleanup(batch_size=5)

        self.assertEqual(result["expired_challenges"], 12)
        statuses = dict(SendVerificationChallenge.objects.values_list("pk", "status"))
        self.assertEqual({statuses[row.pk] for row in overdue}, {"expired"})
        self.assertEqual({statuses[row.pk] for row in live}, {"pending"})
        self.assertEqual(self.cleanup(batch_size=5)["expired_challenges"], 0)

    def test_a_referenced_challenge_is_released_before_its_batch_is_deleted(self):
        (challenge,) = self.make_challenges(1, expires_at=self.old)
        (request,) = self.make_requests(idempotency_expires_at=self.now + timedelta(days=1), challenges=[challenge])

        self.cleanup(batch_size=1)

        request.refresh_from_db()
        self.assertIsNone(request.challenge_id)
        self.assertFalse(SendVerificationChallenge.objects.filter(pk=challenge.pk).exists())

    def test_batch_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            cleanup_expired_records(batch_size=0)

    def test_the_only_relation_to_a_challenge_is_the_set_null_request_link(self):
        """The raw batch DELETE relies on this: a new relation must be handled in ``_delete_old_challenges``."""
        relations = [
            (relation.related_model, relation.field.name, relation.on_delete)
            for relation in SendVerificationChallenge._meta.related_objects
        ]

        self.assertEqual(relations, [(SendVerificationRequest, "challenge", models.SET_NULL)])

    def test_nothing_references_a_send_request(self):
        """``_delete_old_requests`` deletes with one raw DELETE: a new relation must be handled there."""
        self.assertEqual(list(SendVerificationRequest._meta.related_objects), [])


class CleanupQueryBoundTests(CleanupTestCase):
    """Queries grow with the number of batches, never with the rows in a batch."""

    def count_queries(self, *, old_challenges, old_requests, batch_size):
        challenges = self.make_challenges(old_challenges, expires_at=self.old)
        self.make_requests(idempotency_expires_at=self.now + timedelta(days=1), challenges=challenges)
        self.make_requests(old_requests, idempotency_expires_at=self.old)
        with CaptureQueriesContext(connection) as queries:
            self.cleanup(batch_size=batch_size)
        SendVerificationRequest.objects.all().delete()
        return len(queries)

    def test_a_full_batch_costs_the_same_queries_as_a_single_row(self):
        one_row = self.count_queries(old_challenges=1, old_requests=1, batch_size=500)
        full_batch = self.count_queries(old_challenges=500, old_requests=500, batch_size=500)

        self.assertEqual(one_row, full_batch)

    def test_exact_queries_per_batch(self):
        self.make_challenges(11, expires_at=self.old)
        self.make_requests(4, idempotency_expires_at=self.old)

        # 1 settings read + 1 empty pending-expiry probe
        # + 3 challenge batches (4, 4, 3) x [SELECT keys, SAVEPOINT, UPDATE requests, DELETE challenges, RELEASE]
        #   + 1 empty probe
        # + 1 request batch x [SELECT keys, DELETE requests] + 1 empty probe
        with self.assertNumQueries(2 + (3 * 5 + 1) + (1 * 2 + 1)):
            self.cleanup(batch_size=4)

    def test_no_batch_exceeds_the_batch_size(self):
        challenges = self.make_challenges(10, expires_at=self.old)
        self.make_requests(idempotency_expires_at=self.now + timedelta(days=1), challenges=challenges)
        deleted_batches = []
        original = QuerySet._raw_delete

        def spy(queryset, using):
            deleted = original(queryset, using)
            if queryset.model is SendVerificationChallenge:
                deleted_batches.append(deleted)
            return deleted

        with patch.object(QuerySet, "_raw_delete", spy):
            self.cleanup(batch_size=3)

        self.assertEqual(deleted_batches, [3, 3, 3, 1])


def stop_after(checks):
    """A stop check that answers "keep going" ``checks`` times and "stop" from then on."""
    asked = []

    def should_stop():
        asked.append(None)
        return len(asked) > checks

    return should_stop


class CleanupStopRequestTests(CleanupTestCase):
    """A stop request ends the run after the batch in flight; what is left waits for the next run."""

    def backlog(self):
        self.make_challenges(10, expires_at=self.now - timedelta(seconds=1), status="pending")
        self.make_challenges(11, expires_at=self.old)
        self.make_requests(9, idempotency_expires_at=self.old)

    def test_the_run_stops_between_batches_of_the_first_step(self):
        self.backlog()

        result = cleanup_expired_records(now=self.now, batch_size=4, should_stop=stop_after(2))

        # Two batches of four were expired, then the check said stop: the two delete steps did not start.
        self.assertEqual(result, {"expired_challenges": 8, "deleted_challenges": 0, "deleted_requests": 0})
        self.assertEqual(SendVerificationChallenge.objects.filter(status="pending").count(), 2)
        self.assertEqual(SendVerificationChallenge.objects.count(), 21)
        self.assertEqual(SendVerificationRequest.objects.count(), 9)

    def test_the_run_stops_between_batches_of_a_later_step(self):
        self.backlog()

        # Checks: 3 batches + the empty probe of the expiry step, then 2 challenge batches before the stop.
        result = cleanup_expired_records(now=self.now, batch_size=4, should_stop=stop_after(6))

        self.assertEqual(result, {"expired_challenges": 10, "deleted_challenges": 8, "deleted_requests": 0})
        self.assertEqual(SendVerificationChallenge.objects.filter(expires_at__lt=self.old + RETENTION).count(), 3)
        self.assertEqual(SendVerificationRequest.objects.count(), 9)

    def test_the_next_run_finishes_what_a_stopped_run_left(self):
        self.backlog()
        cleanup_expired_records(now=self.now, batch_size=4, should_stop=stop_after(6))

        result = self.cleanup(batch_size=4)

        self.assertEqual(result, {"expired_challenges": 0, "deleted_challenges": 3, "deleted_requests": 9})
        self.assertEqual(SendVerificationChallenge.objects.count(), 10)  # the expired ones, still inside retention
        self.assertFalse(SendVerificationRequest.objects.exists())

    def test_a_stop_request_before_the_first_batch_changes_nothing(self):
        self.backlog()

        with self.assertNumQueries(1):  # the settings read; no batch is even selected
            result = cleanup_expired_records(now=self.now, batch_size=4, should_stop=lambda: True)

        self.assertEqual(result, {"expired_challenges": 0, "deleted_challenges": 0, "deleted_requests": 0})

    def test_a_stop_check_that_never_fires_changes_nothing(self):
        self.backlog()

        result = cleanup_expired_records(now=self.now, batch_size=4, should_stop=lambda: False)

        self.assertEqual(result, {"expired_challenges": 10, "deleted_challenges": 11, "deleted_requests": 9})

    def test_every_batch_is_its_own_transaction(self):
        """A batch that fails takes only itself down: the batches before it stay deleted."""
        self.make_challenges(10, expires_at=self.old)
        original = QuerySet._raw_delete
        calls = []

        def fail_on_the_third_batch(queryset, using):
            calls.append(None)
            if len(calls) == 3:
                raise RuntimeError("database temporarily unavailable")
            return original(queryset, using)

        with patch.object(QuerySet, "_raw_delete", fail_on_the_third_batch), self.assertRaises(RuntimeError):
            self.cleanup(batch_size=3)

        self.assertEqual(SendVerificationChallenge.objects.count(), 4)  # 10 - two committed batches of 3

    def test_expired_sessions_stop_between_batches(self):
        now = timezone.now()
        Session.objects.bulk_create(
            Session(session_key=f"expired{index:02d}".ljust(32, "x"), session_data="e30", expire_date=now - RETENTION)
            for index in range(8)
        )

        cleared = clear_expired_sessions(batch_size=3, should_stop=stop_after(2))

        self.assertEqual(cleared, 6)
        self.assertEqual(Session.objects.count(), 2)
        self.assertEqual(clear_expired_sessions(batch_size=3, should_stop=lambda: True), 0)
        self.assertEqual(clear_expired_sessions(batch_size=3), 2)

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_an_engine_without_rows_ignores_the_stop_check(self):
        self.assertIsNone(clear_expired_sessions(should_stop=lambda: True))


class CleanupCommandTests(CleanupTestCase):
    def test_output_is_unchanged(self):
        self.make_challenges(3, expires_at=self.old)
        self.make_challenges(2, expires_at=self.now - timedelta(seconds=1), status="pending")
        self.make_requests(4, idempotency_expires_at=self.old)
        out = StringIO()

        call_command("cleanup_send_verification", "--batch-size", "2", stdout=out)

        self.assertEqual(out.getvalue().strip(), "Expired 2 challenges; deleted 3 challenges and 4 send requests.")

    def test_default_invocation_still_works(self):
        out = StringIO()

        call_command("cleanup_send_verification", stdout=out)

        self.assertEqual(out.getvalue().strip(), "Expired 0 challenges; deleted 0 challenges and 0 send requests.")

    def test_rejects_a_non_positive_batch_size(self):
        with self.assertRaises(CommandError):
            call_command("cleanup_send_verification", "--batch-size", "0", stdout=StringIO())


class ClearExpiredSessionsTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        now = timezone.now()
        self.expired = [f"expired{index:02d}".ljust(32, "x") for index in range(7)]
        self.live = [f"live{index:02d}".ljust(32, "x") for index in range(3)]
        Session.objects.bulk_create(
            [
                Session(session_key=key, session_data="e30", expire_date=now - timedelta(seconds=1))
                for key in self.expired
            ]
            + [Session(session_key=key, session_data="e30", expire_date=now + timedelta(hours=1)) for key in self.live]
        )

    def test_database_sessions_are_deleted_in_batches(self):
        with CaptureQueriesContext(connection) as queries:
            cleared = clear_expired_sessions(batch_size=3)

        self.assertEqual(cleared, 7)
        self.assertEqual(set(Session.objects.values_list("session_key", flat=True)), set(self.live))
        deletes = [query["sql"] for query in queries if query["sql"].startswith("DELETE")]
        self.assertEqual(len(deletes), 3)  # 3 + 3 + 1

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.cached_db")
    def test_cached_db_sessions_use_the_same_batched_delete(self):
        self.assertEqual(clear_expired_sessions(batch_size=100), 7)
        self.assertEqual(Session.objects.count(), 3)

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_other_engines_use_their_own_clear_expired(self):
        from django.contrib.sessions.backends.signed_cookies import SessionStore

        with patch.object(SessionStore, "clear_expired") as clear_expired:
            self.assertIsNone(clear_expired_sessions())

        clear_expired.assert_called_once_with()
        self.assertEqual(Session.objects.count(), 10)

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_an_engine_that_cannot_clear_is_skipped_like_clearsessions(self):
        from django.contrib.sessions.backends.signed_cookies import SessionStore

        with patch.object(SessionStore, "clear_expired", side_effect=NotImplementedError):
            self.assertIsNone(clear_expired_sessions())

    def test_batch_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            clear_expired_sessions(batch_size=0)
