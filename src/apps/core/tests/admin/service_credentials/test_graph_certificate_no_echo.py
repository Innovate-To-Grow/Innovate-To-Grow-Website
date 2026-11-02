"""The private key and the .p12 / PEM password never leave the install request.

After every install (accepted or refused), rollback and remove, nothing an admin or a later request can read holds
a 32-character slice of the submitted key or the password: the response pages, the session rows, the messages
cookie, anything written to a cache, the admin history, every log record (all loggers at DEBUG, SQL included),
the Graph tables, and the text of every exception the parsing and install code raised.
"""

import contextlib
import logging
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.sessions.models import Session
from django.core import serializers
from django.core.cache import caches
from django.core.signals import got_request_exception
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils.html import escape
from django.views.debug import ExceptionReporter
from rest_framework.test import APIClient

from apps.core.admin.service_credentials import microsoft_graph_certificate_forms as forms_module
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.certificate import describe_certificate
from apps.core.services.email.graph.credential import lifecycle
from apps.core.tests.graph_helpers import make_certificate
from apps.core.tests.services.graph_credential.helpers import entra_rejection
from apps.event.tests.helpers import make_admin

from .graph_certificate_pages import P12_PASSWORD, PASSPHRASE, CertificatePagesMixin, key_pem, pem

CACHE_WRITES = ("set", "add", "set_many", "get_or_set")


def key_slices(*texts):
    """32-character slices of every base64 line of each submitted key text (what a leak would contain)."""
    slices = []
    for text in texts:
        lines = [line for line in text.splitlines() if line and not line.startswith(("-----", "Proc-Type", "DEK-"))]
        slices.extend(line[:32] for line in lines if len(line) >= 32)
    return slices


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.text = []

    def emit(self, record):
        self.text.append(logging.Formatter().format(record))
        self.text.append(repr(record.__dict__))


@contextlib.contextmanager
def every_log_record():
    """Attach one handler to every logger at DEBUG (restoring levels after), so nothing is filtered out."""
    handler = _Records()
    loggers = [logging.getLogger()] + [
        logger for logger in logging.root.manager.loggerDict.values() if isinstance(logger, logging.Logger)
    ]
    saved = [(logger, logger.level, logger.disabled) for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
    try:
        yield handler.text
    finally:
        for logger, level, disabled in saved:
            logger.removeHandler(handler)
            logger.setLevel(level)
            logger.disabled = disabled


class NoEchoTests(CertificatePagesMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.raised = []
        self.cache_writes = []
        for target in (f"{forms_module.__name__}.parse_certificate_input", f"{lifecycle.__name__}.install_certificate"):
            self._spy(target)
        for alias in settings.CACHES:
            backend = type(caches[alias])
            for method in CACHE_WRITES:
                self._record_cache_writes(backend, method)

    def _spy(self, target):
        module_name, name = target.rsplit(".", 1)
        original = getattr(__import__(module_name, fromlist=[name]), name)

        def spy(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            except Exception as exc:
                self.raised.append(exc)
                raise

        self.enterContext(patch(target, spy))

    def _record_cache_writes(self, backend, method):
        original = getattr(backend, method)

        def recording(cache, *args, **kwargs):
            self.cache_writes.append(repr((method, args, kwargs)))
            return original(cache, *args, **kwargs)

        self.enterContext(patch.object(backend, method, recording))

    def submit(self, url, data):
        """POST, then follow the redirect (if any) the way the browser would; return everything readable after."""
        with every_log_record() as logs, CaptureQueriesContext(connection) as queries:
            response = self.client.post(url, data)
            pages = [response.content.decode()]
            if response.status_code == 302:
                pages.append(self.client.get(response["Location"]).content.decode())
        return [
            *pages,
            str(self.client.cookies),
            *logs,
            *(query["sql"] for query in queries.captured_queries),
            *self.cache_writes,
            *self._stored_rows(),
            *self._exception_texts(),
        ]

    def _stored_rows(self):
        sessions = [f"{row.session_data} {row.get_decoded()}" for row in Session.objects.all()]
        history = [f"{entry.object_repr} {entry.change_message}" for entry in LogEntry.objects.all()]
        tables = serializers.serialize(
            "json", [*MicrosoftGraphProviderConfig.objects.all(), *MicrosoftGraphCertificate.objects.all()]
        )
        return [*sessions, *history, tables]

    def _exception_texts(self):
        texts = []
        for exc in self.raised:
            while exc is not None:
                texts.extend((str(exc), repr(exc), repr(exc.args)))
                exc = exc.__cause__ or exc.__context__
        return texts

    def assert_clean(self, readable, *secrets):
        self.assertTrue(secrets)
        for text in readable:
            self.assertNotIn("PRIVATE KEY-----\n", text)
            for secret in secrets:
                self.assertNotIn(secret, text)

    def test_an_accepted_pem_install(self):
        data = self.pem_data()

        readable = self.submit(self.url("install_certificate"), data)

        self.assertIsNotNone(self.config.current_certificate)
        self.assert_clean(readable, *key_slices(data["private_key_text"]))

    def test_a_core_staff_install_keeps_the_key_and_password_out_of_readable_state(self):
        self.client = APIClient()
        self.client.force_login(make_admin(apps=["core"], email="core-no-echo@example.com"))
        data = self.encrypted_pem_data()

        readable = self.submit(self.url("install_certificate"), data)

        self.assertIsNotNone(self.config.current_certificate)
        self.assert_clean(readable, PASSPHRASE, *key_slices(data["private_key_text"]))

    def test_an_accepted_p12_install(self):
        readable = self.submit(self.url("install_certificate"), self.p12_data())

        self.assertIsNotNone(self.config.current_certificate)
        self.assert_clean(readable, P12_PASSWORD, *key_slices(key_pem(self.key)))

    def test_an_accepted_encrypted_pem_install(self):
        data = self.encrypted_pem_data()

        readable = self.submit(self.url("install_certificate"), data)

        self.assertIsNotNone(self.config.current_certificate)
        self.assert_clean(readable, PASSPHRASE, *key_slices(data["private_key_text"], key_pem(self.key)))

    def test_refused_installs(self):
        _other, other_key = make_certificate(key_index=1)
        encrypted = self.encrypted_pem_data()
        cases = {
            "wrong passphrase": encrypted | {"password": "wrong-" + PASSPHRASE},
            "key of another certificate": self.pem_data(key=other_key),
            "key in the certificate box": {"certificate_text": key_pem(self.key) + pem(self.certificate)},
            "key in both boxes": {"certificate_text": key_pem(self.key), "private_key_text": key_pem(self.key)},
            "wrong .p12 password": self.p12_data() | {"password": "wrong-" + P12_PASSWORD},
        }
        keys = [key_pem(self.key), key_pem(other_key), encrypted["private_key_text"]]
        for name, data in cases.items():
            with self.subTest(name):
                readable = self.submit(self.url("install_certificate"), data)

                self.assertIsNone(self.config.current_certificate)
                self.assertTrue(self.raised)
                # The wrong passwords contain the right ones, so these cover both.
                self.assert_clean(readable, P12_PASSWORD, PASSPHRASE, *key_slices(*keys))

    def test_a_key_pasted_into_the_thumbprint_box_is_not_echoed(self):
        key = key_pem(self.key)
        # A single-line input drops the line breaks of what is pasted into it.
        for name, pasted in (("PEM", key), ("one line", "".join(key.splitlines()))):
            with self.subTest(name):
                readable = self.submit(self.url("install_certificate"), self.pem_data() | {"expected_sha1": pasted})

                self.assertIsNone(self.config.current_certificate)
                self.assertIn(forms_module.THUMBPRINT_FORMAT, readable[0])
                self.assert_clean(readable, *key_slices(key))
                for text in readable:
                    self.assertNotIn("BEGIN PRIVATE KEY", text)

    def test_a_well_formed_thumbprint_is_shown_again_normalised(self):
        other = describe_certificate(make_certificate(key_index=1)[0]).sha1_thumbprint
        typed = ":".join(other[index : index + 2] for index in range(0, len(other), 2)).lower()

        response = self.client.post(self.url("install_certificate"), self.pem_data() | {"expected_sha1": typed})

        self.assertContains(response, escape(forms_module.THUMBPRINT_MISMATCH))
        self.assertContains(response, f'value="{other}"')

    def test_an_install_entra_refuses(self):
        self.script(token=entra_rejection(700027))
        data = self.pem_data()

        readable = self.submit(self.url("install_certificate"), data)

        self.assertIsNone(self.config.current_certificate)
        self.assert_clean(readable, *key_slices(data["private_key_text"]))

    def test_rollback_and_remove(self):
        _first, first_key = self.install_existing()
        _second, second_key = self.install_existing(key_index=1)
        secrets = key_slices(key_pem(first_key), key_pem(second_key))

        self.assert_clean(self.submit(self.url("rollback_certificate"), {}), *secrets)
        removal = {"confirmation": "REMOVE", "reason": "Rotation drill"}
        self.assert_clean(self.submit(self.url("remove_certificates"), removal), *secrets)
        self.assertIsNone(self.config.current_certificate)


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
