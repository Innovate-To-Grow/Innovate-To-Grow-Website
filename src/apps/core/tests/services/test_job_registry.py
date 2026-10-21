from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.utils.module_loading import import_string

from apps.core.services.background_jobs import registry
from apps.core.services.background_jobs.registry import (
    get_handler,
    notify_job_state,
    register_job_kind,
    registered_job_kinds,
    resolve_stale_job_state,
)

EXPECTED_KINDS = {
    "authn.member_sheet_sync",
    "authn.notification_email",
    "cms.amplify_redirects",
    "event.registration_sheet_sync",
    "event.ticket_email",
    "mail.email_recipient",
    "mail.sms_recipient",
}


class RegisteredJobKindsTests(SimpleTestCase):
    """The owning apps register every job kind the codebase enqueues, at importable paths."""

    def test_every_job_kind_is_registered_by_its_app(self):
        self.assertEqual(set(registered_job_kinds()), EXPECTED_KINDS)

    def test_every_registered_path_imports(self):
        for kind, entry in registered_job_kinds().items():
            for path in filter(None, (entry.handler, entry.state_handler, entry.stale_resolver)):
                with self.subTest(kind=kind, path=path):
                    self.assertTrue(callable(import_string(path)))

    def test_delivery_kinds_mirror_state_and_resolve_stale_jobs(self):
        kinds = registered_job_kinds()
        for kind in ("mail.email_recipient", "mail.sms_recipient"):
            self.assertIsNotNone(kinds[kind].stale_resolver)
            self.assertIsNotNone(kinds[kind].state_handler)
        self.assertIsNone(kinds["event.ticket_email"].state_handler)


class RegisterJobKindTests(SimpleTestCase):
    def setUp(self):
        patcher = patch.dict(registry._KINDS, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reregistering_identical_paths_is_idempotent(self):
        register_job_kind("test.kind", handler="builtins.print")
        register_job_kind("test.kind", handler="builtins.print")
        self.assertEqual(registered_job_kinds()["test.kind"].handler, "builtins.print")

    def test_conflicting_registration_is_rejected(self):
        register_job_kind("test.kind", handler="builtins.print")
        with self.assertRaises(ImproperlyConfigured):
            register_job_kind("test.kind", handler="builtins.repr")

    def test_unknown_kind_has_no_handler(self):
        with self.assertRaises(LookupError):
            get_handler("test.unknown")

    def test_optional_hooks_are_skipped_when_not_registered(self):
        register_job_kind("test.kind", handler="builtins.print")
        job = SimpleNamespace(kind="test.kind")
        self.assertIsNone(notify_job_state(job))
        self.assertIsNone(resolve_stale_job_state(job))
        self.assertIsNone(resolve_stale_job_state(SimpleNamespace(kind="test.unknown")))

    def test_hooks_resolve_their_dotted_paths(self):
        register_job_kind(
            "test.kind",
            handler="builtins.print",
            state_handler="builtins.id",
            stale_resolver="builtins.str",
        )
        job = SimpleNamespace(kind="test.kind")
        self.assertIs(get_handler("test.kind"), print)
        notify_job_state(job)
        self.assertEqual(resolve_stale_job_state(job), str(job))
