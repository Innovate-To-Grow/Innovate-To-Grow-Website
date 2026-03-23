from unittest.mock import patch

from django.test import TestCase

# noinspection PyProtectedMember
from analytics.models import PageView
from analytics.services.buffer import _BATCH_SIZE, enqueue, flush_sync


class PageViewBufferTest(TestCase):
    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()

    # noinspection PyMethodMayBeStatic,PyPep8Naming
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
        """Enqueue should spawn a flush thread when buffer reaches _BATCH_SIZE."""
        # Ensure the timer is already initialized so we can patch Thread cleanly.
        enqueue({"path": "/init", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""})

        with patch("analytics.services.buffer.threading.Thread") as mock_thread_cls:
            for i in range(_BATCH_SIZE):
                enqueue(
                    {"path": f"/page-{i}", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
                )

            mock_thread_cls.assert_called()
            mock_thread_cls.return_value.start.assert_called()

        flush_sync()
        # 1 init + _BATCH_SIZE
        self.assertEqual(PageView.objects.count(), _BATCH_SIZE + 1)

    def test_flush_sync_clears_buffer(self):
        enqueue({"path": "/x", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""})
        flush_sync()
        self.assertEqual(PageView.objects.count(), 1)

        # Second flush should be a no-op
        flush_sync()
        self.assertEqual(PageView.objects.count(), 1)

    @patch("analytics.services.buffer._MAX_BUFFER_SIZE", 5)
    def test_buffer_overflow_drops_oldest(self):
        """When buffer exceeds _MAX_BUFFER_SIZE, oldest entries are dropped."""
        for i in range(8):
            enqueue(
                {"path": f"/page-{i}", "referrer": "", "ip_address": "1.2.3.4", "user_agent": "", "session_key": ""}
            )

        flush_sync()
        # Only the last 5 should survive
        self.assertEqual(PageView.objects.count(), 5)
        paths = set(PageView.objects.values_list("path", flat=True))
        self.assertEqual(paths, {"/page-3", "/page-4", "/page-5", "/page-6", "/page-7"})
