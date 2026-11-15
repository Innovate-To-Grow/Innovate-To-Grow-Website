from apps.authn.services.security import login_guard
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_SPRAY_WINDOW

from .login_guard_helpers import LOGGER, PHONE, THRESHOLD, GuardTestCase, identifier_rows, spray_count


class SprayDetectionTests(GuardTestCase):
    """Site-wide failure spikes are logged once per window for an alarm and never refuse anyone."""

    def spray(self, count, start=0):
        for index in range(start, start + count):
            login_guard.record_failure(f"member{index}@example.com")

    @staticmethod
    def spikes(logs):
        return [record for record in logs.records if record.getMessage().startswith("login_guard.failure_spike")]

    def test_one_warning_when_the_site_wide_count_reaches_the_threshold(self):
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.spray(THRESHOLD - 1)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(1, start=THRESHOLD - 1)

        self.assertEqual(len(logs.records), 1)
        self.assertEqual(
            logs.records[0].getMessage(),
            f"login_guard.failure_spike failures={THRESHOLD} window=5m threshold={THRESHOLD}",
        )

    def test_the_warning_fires_once_per_window_and_again_in_the_next(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(THRESHOLD + 50)
        self.assertEqual(len(self.spikes(logs)), 1)
        self.assertEqual(spray_count(), THRESHOLD + 50)

        self.clock.advance(SECONDS_LEFT_IN_SPRAY_WINDOW)
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(THRESHOLD, start=THRESHOLD + 50)

        self.assertEqual(len(self.spikes(logs)), 1)
        self.assertEqual(spray_count(), THRESHOLD)

    def test_a_spray_never_locks_anyone(self):
        with self.assertLogs(LOGGER, "WARNING"):
            self.spray(THRESHOLD + 50)

        for identifier in ("member0@example.com", f"member{THRESHOLD}@example.com", "fresh@example.com", PHONE):
            with self.subTest(identifier=identifier):
                self.assertEqual(login_guard.retry_after(identifier), 0)
                login_guard.ensure_not_locked(identifier)

    def test_the_warning_names_no_identifier_and_no_digest(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(THRESHOLD)

        (record,) = self.spikes(logs)
        text = f"{record.getMessage()} {record.args}"
        digests = set(identifier_rows().values_list("identifier_digest", flat=True))
        self.assertEqual(len(digests), THRESHOLD)
        for fragment in ("member", "example", "@", *(digest[:12] for digest in digests)):
            self.assertNotIn(fragment, text)
        self.assertTrue(all(isinstance(arg, (int, str)) and str(arg) in {"5m", str(THRESHOLD)} for arg in record.args))

    def test_failures_against_one_identifier_count_towards_the_spike_too(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(THRESHOLD - 1, "one@example.com")
        self.assertEqual(len(logs.records), 2)  # its own 15-minute and daily locks, no spike yet
        self.assertEqual(self.spikes(logs), [])

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(1, "two@example.com")

        self.assertEqual(len(self.spikes(logs)), 1)

    def test_a_success_does_not_reset_the_site_wide_count(self):
        self.spray(THRESHOLD - 1)
        for index in range(THRESHOLD - 1):
            login_guard.clear(f"member{index}@example.com")

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(1, start=THRESHOLD)

        self.assertEqual(len(self.spikes(logs)), 1)

    def test_blank_identifiers_are_not_counted(self):
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.record(THRESHOLD + 10, "   ")

        self.assertEqual(spray_count(), 0)
