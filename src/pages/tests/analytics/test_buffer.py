from unittest.mock import patch

from django.test import TestCase

from pages.models import PageView
from pages.services.analytics.buffer import _BATCH_SIZE, enqueue, flush_sync


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

        with patch("pages.services.analytics.buffer.threading.Thread") as mock_thread_cls:
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

    @patch("pages.services.analytics.buffer._MAX_BUFFER_SIZE", 5)
    def test_buffer_overflow_drops_oldest(self):
        for i in range(8):
            enqueue(
                {"path": f"/page-{i}", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
            )

        flush_sync()
        self.assertEqual(PageView.objects.count(), 5)
        paths = set(PageView.objects.values_list("path", flat=True))
        self.assertEqual(paths, {"/page-3", "/page-4", "/page-5", "/page-6", "/page-7"})
