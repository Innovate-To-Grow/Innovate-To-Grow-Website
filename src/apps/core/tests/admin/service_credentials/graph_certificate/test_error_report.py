from unittest.mock import patch

from django.core.signals import got_request_exception
from django.test import TestCase
from django.views.debug import ExceptionReporter

from apps.core.services.email.graph.credential import lifecycle
from apps.core.tests.admin.service_credentials.graph_certificate.test_graph_certificate_no_echo import key_slices

from .graph_certificate_pages import PASSPHRASE, CertificatePagesMixin, key_pem


class ErrorReportTests(CertificatePagesMixin, TestCase):
    """An unexpected error during an install: the error report (500 email / log) hides the POST data and locals."""

    def test_the_error_report_hides_the_submitted_key_and_password(self):
        requests = []
        uid = "graph-certificate-error-report-test"
        got_request_exception.connect(lambda request, **kwargs: requests.append(request), weak=False, dispatch_uid=uid)
        self.addCleanup(got_request_exception.disconnect, dispatch_uid=uid)
        data = self.encrypted_pem_data()

        with (
            patch(f"{lifecycle.__name__}.install_certificate", side_effect=RuntimeError("unexpected")),
            self.assertRaises(RuntimeError) as caught,
        ):
            self.client.post(self.url("install_certificate"), data)

        exc = caught.exception
        report = ExceptionReporter(requests[0], type(exc), exc, exc.__traceback__, is_email=True)
        text = report.get_traceback_text()
        self.assertIn("RuntimeError", text)
        self.assertIn("private_key_text", text)  # the POST section lists the names...
        self.assertNotIn(PASSPHRASE, text)  # ...but none of the values, and no frame's locals
        for secret in key_slices(data["private_key_text"], key_pem(self.key)):
            self.assertNotIn(secret, text)
