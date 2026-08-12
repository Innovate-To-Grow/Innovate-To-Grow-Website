"""PostgreSQL concurrency coverage for optimistic PastProjectShare updates."""

import threading
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.projects.models import PastProjectShare
from apps.projects.serializers import PastProjectShareSerializer
from apps.projects.tests.api.test_past_project_share import sample_row

Member = get_user_model()


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL concurrent update semantics")
class PastProjectShareConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.member = Member.objects.create_user(password="SharePass123!", is_active=True)
        self.share = PastProjectShare.objects.create(
            name="Concurrent share",
            rows=[sample_row()],
            created_by=self.member,
        )

    def test_concurrent_patch_with_same_version_accepts_exactly_one(self):
        both_ready = threading.Event()
        release_updates = threading.Event()
        state_lock = threading.Lock()
        ready_count = 0
        responses = {}
        errors = {}
        original_update = PastProjectShareSerializer.update

        def synchronized_update(serializer, instance, validated_data):
            nonlocal ready_count
            with state_lock:
                ready_count += 1
                if ready_count == 2:
                    both_ready.set()
            if not release_updates.wait(timeout=10):
                raise TimeoutError("concurrent PastProjectShare updates were not released")
            return original_update(serializer, instance, validated_data)

        def patch_share(label):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user=Member.objects.get(pk=self.member.pk))
                responses[label] = client.patch(
                    f"/projects/past-shares/{self.share.pk}/",
                    {"note": f"Edit {label}", "version": 1},
                    format="json",
                )
            except Exception as exc:  # noqa: BLE001 - reported by the main test thread.
                errors[label] = exc
            finally:
                connections.close_all()

        with patch.object(PastProjectShareSerializer, "update", synchronized_update):
            threads = [threading.Thread(target=patch_share, args=(label,)) for label in ("A", "B")]
            for thread in threads:
                thread.start()
            self.assertTrue(both_ready.wait(timeout=10), errors)
            release_updates.set()
            for thread in threads:
                thread.join(timeout=10)

        for thread in threads:
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, {})
        self.assertEqual(sorted(response.status_code for response in responses.values()), [200, 409])

        winner = next(response for response in responses.values() if response.status_code == 200)
        loser = next(response for response in responses.values() if response.status_code == 409)
        self.assertEqual(loser.data["code"], "stale_snapshot")
        current = loser.data["current"]
        self.assertEqual(current["id"], winner.data["id"])
        self.assertEqual(current["note"], winner.data["note"])
        self.assertEqual(current["version"], winner.data["version"])
        self.share.refresh_from_db()
        self.assertEqual(self.share.version, 2)
        self.assertEqual(self.share.note, winner.data["note"])
        self.assertEqual(self.share.note, current["note"])
