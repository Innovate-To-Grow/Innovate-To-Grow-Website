from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from apps.cms.models import PageView
from apps.cms.services.analytics import buffer as buffer_module
from apps.cms.services.analytics.buffer import (
    _BATCH_SIZE,
    _do_bulk_insert,
    _flush,
    _schedule_flush_locked,
    enqueue,
    flush_sync,
)


class PageViewBufferTest(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()

    def tearDown(self):
        flush_sync()

    def test_enqueue_and_flush(self):
        enqueue({"path": "/test", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""})
        enqueue({"path": "/test2", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""})

        flush_sync()
        self.assertEqual(PageView.objects.count(), 2)
        self.assertEqual(set(PageView.objects.values_list("path", flat=True)), {"/test", "/test2"})

    def test_flush_empty_buffer(self):
        flush_sync()
        self.assertEqual(PageView.objects.count(), 0)

    def test_auto_flush_triggered_at_batch_size(self):
        enqueue({"path": "/init", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""})

        with patch("apps.cms.services.analytics.buffer.threading.Thread") as mock_thread_cls:
            for i in range(_BATCH_SIZE):
                enqueue(
                    {"path": f"/page-{i}", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
                )
            mock_thread_cls.assert_called()
            mock_thread_cls.return_value.start.assert_called()

        flush_sync()
        self.assertEqual(PageView.objects.count(), _BATCH_SIZE + 1)

    def test_flush_sync_clears_buffer(self):
        enqueue({"path": "/x", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""})
        flush_sync()
        self.assertEqual(PageView.objects.count(), 1)

        flush_sync()
        self.assertEqual(PageView.objects.count(), 1)

    @patch("apps.cms.services.analytics.buffer._MAX_BUFFER_SIZE", 5)
    def test_buffer_overflow_drops_oldest(self):
        for i in range(8):
            enqueue(
                {"path": f"/page-{i}", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
            )

        flush_sync()
        self.assertEqual(PageView.objects.count(), 5)
        paths = set(PageView.objects.values_list("path", flat=True))
        self.assertEqual(paths, {"/page-3", "/page-4", "/page-5", "/page-6", "/page-7"})


class DoBulkInsertTests(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()

    def tearDown(self):
        flush_sync()

    def test_bulk_insert_writes_rows(self):
        batch = [
            {"path": "/a", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""},
            {"path": "/b", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""},
        ]
        _do_bulk_insert(batch)
        self.assertEqual(PageView.objects.count(), 2)

    def test_bulk_insert_retries_then_succeeds(self):
        batch = [{"path": "/retry", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}]
        real_bulk_create = PageView.objects.bulk_create
        calls = {"n": 0}

        def flaky_bulk_create(objs, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise DatabaseError("transient")
            return real_bulk_create(objs, *args, **kwargs)

        with (
            patch.object(PageView.objects, "bulk_create", side_effect=flaky_bulk_create),
            patch("apps.cms.services.analytics.buffer.logger") as mock_logger,
        ):
            _do_bulk_insert(batch)
            mock_logger.warning.assert_called_once()

        self.assertEqual(calls["n"], 2)
        self.assertEqual(PageView.objects.count(), 1)

    def test_bulk_insert_drops_batch_after_max_retries(self):
        batch = [{"path": "/fail", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}]

        with (
            patch.object(PageView.objects, "bulk_create", side_effect=DatabaseError("down")),
            patch("apps.cms.services.analytics.buffer.logger") as mock_logger,
        ):
            _do_bulk_insert(batch)
            mock_logger.exception.assert_called_once()

        self.assertEqual(PageView.objects.count(), 0)


class FlushTests(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()

    def tearDown(self):
        flush_sync()

    def test_flush_inserts_and_reschedules(self):
        buffer_module._buffer.append(
            {"path": "/flush-me", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
        )
        buffer_module._flush_done.set()

        with patch("apps.cms.services.analytics.buffer._schedule_flush_locked") as mock_schedule:
            _flush()
            mock_schedule.assert_called_once()

        self.assertEqual(PageView.objects.count(), 1)
        # done flag is restored after insert completes
        self.assertTrue(buffer_module._flush_done.is_set())

    def test_flush_skips_when_flush_in_progress(self):
        buffer_module._buffer.append(
            {"path": "/skip", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
        )
        buffer_module._flush_done.clear()  # simulate in-progress flush

        with (
            patch("apps.cms.services.analytics.buffer._schedule_flush_locked") as mock_schedule,
            patch("apps.cms.services.analytics.buffer._do_bulk_insert") as mock_insert,
        ):
            _flush()
            mock_schedule.assert_called_once()
            mock_insert.assert_not_called()

        # buffer untouched because flush was skipped
        self.assertEqual(len(buffer_module._buffer), 1)
        buffer_module._buffer.clear()
        buffer_module._flush_done.set()

    def test_flush_reschedules_when_buffer_empty(self):
        buffer_module._buffer.clear()
        buffer_module._flush_done.set()

        with (
            patch("apps.cms.services.analytics.buffer._schedule_flush_locked") as mock_schedule,
            patch("apps.cms.services.analytics.buffer._do_bulk_insert") as mock_insert,
        ):
            _flush()
            mock_schedule.assert_called_once()
            mock_insert.assert_not_called()


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
