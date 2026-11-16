from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.authn.services.sms import latency


class LatencyTests(SimpleTestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        latency.reset()
        self.addCleanup(latency.reset)

    @override_settings(SMS_WITHHELD_SEND_DELAY_SECONDS=(0.4, 0.4))
    def test_without_sends_the_delay_comes_from_the_setting(self):
        self.assertEqual(latency.send_delay(), 0.4)

    @override_settings(SMS_WITHHELD_SEND_DELAY_SECONDS=(0.1, 0.3))
    def test_the_fallback_delay_stays_in_its_range(self):
        delays = {latency.send_delay() for _ in range(50)}

        self.assertTrue(all(0.1 <= delay <= 0.3 for delay in delays))

    def test_a_malformed_setting_falls_back_to_the_default_range(self):
        low, high = latency.DEFAULT_DELAY_RANGE
        for value in (None, "fast", (0.5,), (-1, 2), (2, 1)):
            with self.subTest(value=value), override_settings(SMS_WITHHELD_SEND_DELAY_SECONDS=value):
                self.assertTrue(low <= latency.send_delay() <= high)

    def test_recorded_sends_are_what_the_delay_is_drawn_from(self):
        for seconds in (0.11, 0.22, -1):
            latency.observe_send(seconds)

        self.assertEqual(list(latency._samples), [0.11, 0.22])  # a negative duration is not a duration
        self.assertTrue({latency.send_delay() for _ in range(50)} <= {0.11, 0.22})

    def test_only_the_latest_sends_are_kept(self):
        for index in range(latency.SAMPLE_SIZE + 5):
            latency.observe_send(index)

        self.assertEqual(len(latency._samples), latency.SAMPLE_SIZE)
        self.assertEqual(latency._samples[0], 5)

    def test_waiting_goes_through_the_limiter_sleep(self):
        latency.observe_send(0.25)

        with patch.object(latency.context, "sleep") as sleep:
            latency.wait_like_a_send()

        sleep.assert_called_once_with(0.25)
