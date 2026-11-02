"""The background worker's hourly "Microsoft Graph certificate expiry check": one fixed WARNING line from
``GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS`` before expiry, nothing otherwise."""

import datetime

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.management.commands import run_background_worker
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.credential import expiry
from apps.core.tests.graph_helpers import create_graph_config

LOGGER = "apps.core.management.commands.run_background_worker"
HOUR = datetime.timedelta(hours=1)
PREFIX = "Microsoft Graph certificate expiry warning: "


class GraphCertificateExpiryMaintenanceTests(TestCase):
    def setUp(self):
        self.config = create_graph_config(scope=("i2g@contoso.com",), name="Graph", is_active=True)

    def expire_in(self, delta):
        MicrosoftGraphCertificate.objects.filter(config=self.config).update(not_after=timezone.now() + delta)

    def run_check(self):
        run_background_worker._check_graph_certificate_expiry()

    def test_inside_the_warning_window_one_fixed_line_is_logged(self):
        days = settings.GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS - 1
        self.expire_in(datetime.timedelta(days=days) + HOUR)

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.run_check()

        self.assertEqual(
            [(record.levelname, record.getMessage()) for record in logs.records],
            [("WARNING", f"{PREFIX}{days} days left; install the renewed certificate")],
        )
        self.assertEqual(logs.records[0].msg, run_background_worker.GRAPH_EXPIRY_WARNING)

    def test_an_expired_certificate_logs_the_expired_line(self):
        self.expire_in(-HOUR)

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.run_check()

        self.assertEqual(logs.records[0].getMessage(), f"{PREFIX}expired; install the renewed certificate")

    def test_outside_the_window_without_a_certificate_or_config_nothing_is_logged(self):
        self.expire_in(datetime.timedelta(days=settings.GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS + 1) + HOUR)
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_check()

        self.config.certificates.update(state="removed")
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_check()

        MicrosoftGraphProviderConfig.objects.update(is_active=False)
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_check()

    @override_settings(GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS=5, GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS=2)
    def test_the_window_comes_from_settings(self):
        self.expire_in(datetime.timedelta(days=10) + HOUR)
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_check()

        self.expire_in(datetime.timedelta(days=4) + HOUR)
        with self.assertLogs(LOGGER, level="WARNING"):
            self.run_check()

    def test_it_runs_with_the_other_maintenance_tasks(self):
        self.assertIn(
            ("Microsoft Graph certificate expiry check", run_background_worker._check_graph_certificate_expiry),
            run_background_worker.MAINTENANCE_TASKS,
        )


@override_settings(GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS=60, GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS=14)
class CertificateExpiryLevelTests(TestCase):
    """The one rule the admin badge, ``verify_service_configs`` and the worker share."""

    def setUp(self):
        self.certificate = create_graph_config(name="Graph").current_certificate
        self.now = timezone.now()

    def level(self, *, days_left=None, starts_in=None):
        if days_left is not None:
            self.certificate.not_after = self.now + days_left
        if starts_in is not None:
            self.certificate.not_before = self.now + starts_in
        return expiry.certificate_expiry(self.certificate, now=self.now)

    def test_each_threshold(self):
        day = datetime.timedelta(days=1)
        cases = (
            (61 * day, expiry.OK, 61),
            (60 * day + HOUR, expiry.WARNING, 60),
            (15 * day, expiry.WARNING, 15),
            (14 * day + HOUR, expiry.CRITICAL, 14),
            (HOUR, expiry.CRITICAL, 0),
            (-HOUR, expiry.EXPIRED, -1),
        )
        for delta, level, days_left in cases:
            with self.subTest(delta=delta):
                self.assertEqual(self.level(days_left=delta), expiry.Expiry(level, days_left))

    def test_a_certificate_that_is_not_valid_yet(self):
        self.assertEqual(self.level(starts_in=HOUR).level, expiry.NOT_YET_VALID)

    def test_local_time_names_the_site_zone(self):
        text = expiry.local_time_text(datetime.datetime(2027, 10, 29, 18, 0, tzinfo=datetime.UTC))

        self.assertEqual(text, "2027-10-29 11:00 PDT")
