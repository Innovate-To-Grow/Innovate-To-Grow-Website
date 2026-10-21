"""Shared fixtures for the login-guard tests."""

from datetime import UTC, datetime

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.clock import (
    freeze_time,
)

EMAIL = "victim@example.com"


GLOBAL = LoginFailureWindow.GLOBAL_DIGEST


LOGGER = "apps.authn.services.login_guard"


PHONE = "(209) 555-1234"


SCOPE = "admin-remembered"


SUBJECT = "0b9c2a4e-5f6d-4c3b-8a1e-2d3f4a5b6c7d"


THRESHOLD = login_guard.SPRAY_ALERT_THRESHOLD


# What a client could type into an identifier field while aiming at the scoped counter of SUBJECT.
TYPED_AT_THE_SCOPED_KEY = (
    f"{SCOPE}:{SUBJECT}",  # the exact text the scoped key hashes
    f" {SCOPE}:{SUBJECT} ",
    f"{SCOPE}:{SUBJECT}".upper(),
    f"{SCOPE}:{SUBJECT}@",
    f"{SCOPE}:{SUBJECT}@example.com",
    f"admin-member:{SUBJECT}@",
    f"scope:{SCOPE}:{SUBJECT}",
    f"email:{SCOPE}:{SUBJECT}",
    f"phone:{SCOPE}:{SUBJECT}",
    f"other:{SCOPE}:{SUBJECT}",
    f"ScopedKey(scope='{SCOPE}', subject='{SUBJECT}')",
    SUBJECT,
    SUBJECT.replace("-", ""),
    SCOPE,
    f"{SCOPE}:",
    f"{SCOPE}:no digits here",
    "login-guard.scope",
    EMAIL,
    PHONE,
    "+1 209 555 1234",
    "just some text",
    "global",
)


def at(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)


def identifier_rows():
    return LoginFailureWindow.objects.exclude(identifier_digest=GLOBAL)


def spray_count() -> int:
    row = LoginFailureWindow.objects.filter(identifier_digest=GLOBAL).order_by("-window_index").first()
    return row.failure_count if row else 0


class GuardTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.clock = freeze_time(self)

    def record(self, times, identifier=EMAIL):
        for _ in range(times):
            login_guard.record_failure(identifier)
