from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, transaction
from django.test import TransactionTestCase

from apps.core.models import BackgroundJob
from apps.event.models import (
    Event,
    RegistrationSheetSyncConfig,
)
from apps.event.services.registration_sheet_sync.scheduler import (
    JOB_KIND,
    schedule_registration_sync,
)
from apps.event.tests.helpers import make_event


class RegistrationSheetSchedulerConcurrencyTest(TransactionTestCase):
    def setUp(self):
        cache.clear()
        # Real commits would start the no-worker fallback thread, which races teardown.
        fallback = patch("apps.event.services.registration_sheet_sync.append._schedule_in_process_sync")
        fallback.start()
        self.addCleanup(fallback.stop)
        if connection.vendor != "postgresql":
            self.skipTest("Real row-lock behavior requires PostgreSQL.")
        self.event = make_event()
        Event.objects.filter(pk=self.event.pk).update(registration_sheet_id="concurrency-sheet")
        self.event.refresh_from_db()

    def schedule_in_worker(self):
        from django.db import close_old_connections

        close_old_connections()
        try:
            schedule_registration_sync(self.event)
        finally:
            connection.close()

    def test_concurrent_first_requests_share_one_configuration_and_one_job(self):
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.schedule_in_worker(), range(12)))
        config = RegistrationSheetSyncConfig.objects.get(event=self.event)
        self.assertEqual(config.requested_generation, 12)
        self.assertEqual(BackgroundJob.objects.filter(kind=JOB_KIND).count(), 1)

    def test_provider_event_lock_does_not_block_source_scheduling(self):
        from concurrent.futures import ThreadPoolExecutor

        RegistrationSheetSyncConfig.objects.create(event=self.event)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Event.objects.select_for_update(no_key=True).get(pk=self.event.pk)
                result = pool.submit(self.schedule_in_worker)
                result.result(timeout=5)
        self.assertEqual(RegistrationSheetSyncConfig.objects.get(event=self.event).requested_generation, 1)
