from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from apps.cms.models import PageView
from apps.cms.services.analytics import buffer as buffer_module
from apps.cms.services.analytics.buffer import (
    _schedule_flush_locked,
    flush_sync,
)


class ScheduleFlushTests(TestCase):
    def tearDown(self):
        flush_sync()

    def test_schedule_cancels_existing_timer(self):
        sentinel_timer = patch("apps.cms.services.analytics.buffer.threading.Timer").start()
        self.addCleanup(patch.stopall)

        # First schedule creates a timer.
        _schedule_flush_locked()
        first_timer = buffer_module._timer
        self.assertIsNotNone(first_timer)

        # Second schedule must cancel the existing timer before replacing it.
        _schedule_flush_locked()
        first_timer.cancel.assert_called_once()


class FlushSyncErrorTests(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()

    def tearDown(self):
        flush_sync()

    def test_flush_sync_logs_on_database_error(self):
        buffer_module._buffer.append(
            {"path": "/err", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
        )
        buffer_module._flush_done.set()

        with (
            patch.object(PageView.objects, "bulk_create", side_effect=DatabaseError("nope")),
            patch("apps.cms.services.analytics.buffer.logger") as mock_logger,
        ):
            flush_sync()
            mock_logger.exception.assert_called_once()

        # batch was consumed even though the insert failed
        self.assertEqual(len(buffer_module._buffer), 0)
        self.assertEqual(PageView.objects.count(), 0)
