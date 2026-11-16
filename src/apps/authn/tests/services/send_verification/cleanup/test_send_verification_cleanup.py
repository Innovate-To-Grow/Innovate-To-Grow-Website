"""Batched retention cleanup for send-verification rows and expired sessions."""

import uuid
from datetime import timedelta

from django.core.cache import cache
from django.db import models
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest
from apps.authn.services.send_verification import cleanup_expired_records

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


def stop_after(checks):
    """A stop check that answers "keep going" ``checks`` times and "stop" from then on."""
    asked = []

    def should_stop():
        asked.append(None)
        return len(asked) > checks

    return should_stop
