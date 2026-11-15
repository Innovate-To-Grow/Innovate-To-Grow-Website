"""The project's test runner: Django's own, with the delivery-rate limiter on a virtual clock.

Every email goes through the limiter, which sleeps until each message's slot (a fresh test database starts Smart
rate on its fallbacks, under one SES message a second). Tests of other features must not wait for real, so a limiter
sleep moves the limiter's clock forward instead: pacing still decides the order and every deferral, but costs no
time. The clock starts again at real time with every test. The limiter's own tests install ``FakeClock`` on top.
"""

import threading
import unittest
from datetime import timedelta
from unittest.mock import patch

from django.test.runner import DiscoverRunner
from django.utils import timezone

from apps.core.services.delivery_rates.runtime import context


class VirtualClock:
    """``timezone.now()`` plus the time every limiter sleep in the current test has skipped."""

    def __init__(self):
        self._offset = timedelta(0)
        self._lock = threading.Lock()

    def now(self):
        with self._lock:
            return timezone.now() + self._offset

    def sleep(self, seconds):
        with self._lock:
            self._offset += timedelta(seconds=max(0.0, float(seconds)))

    def reset(self):
        with self._lock:
            self._offset = timedelta(0)


CLOCK = VirtualClock()


class _ResetsTheClock:
    def startTest(self, test):
        CLOCK.reset()
        super().startTest(test)


class ProjectTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._clock_patches = [patch.object(context, "clock", CLOCK.now), patch.object(context, "sleep", CLOCK.sleep)]
        for patcher in self._clock_patches:
            patcher.start()

    def teardown_test_environment(self, **kwargs):
        for patcher in reversed(getattr(self, "_clock_patches", [])):
            patcher.stop()
        super().teardown_test_environment(**kwargs)

    def get_resultclass(self):
        base = super().get_resultclass() or unittest.TextTestResult
        return type(f"VirtualClock{base.__name__}", (_ResetsTheClock, base), {})
