"""The Gmail API config admin: Core app (like the other provider configs), the key pages (install, remove, access
check), no echo of a submitted key anywhere, and the changelist lookup guard."""

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import GmailApiSubject
from apps.core.tests.gmail_api_helpers import (
    SUBJECT,
    make_config,
    reset_gmail_state,
)
from apps.event.tests.helpers import make_admin, make_superuser

PREFIX = "admin:core_gmailapiproviderconfig"


def pem_slices(text: str, size: int = 20) -> list[str]:
    """20-character slices of every base64 line of a PEM key (what any leak would contain)."""
    lines = [line for line in text.splitlines() if line and not line.startswith("-----")]
    return [line[start : start + size] for line in lines for start in range(0, len(line) - size + 1, size)]


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class GmailAdminTestCase(TestCase):
    def setUp(self):
        cache.clear()
        reset_gmail_state()
        self.superuser = make_superuser()
        self.config = make_config(active=False, key=False)

    def url(self, name, config=None):
        return reverse(f"{PREFIX}_{name}", args=[(config or self.config).pk])


class CoreAppAccessTests(GmailAdminTestCase):
    """The Gmail API config needs the Core app, like the other provider configs: Core staff manage it fully."""

    def pages(self):
        return {
            "changelist": reverse(f"{PREFIX}_changelist"),
            "add": reverse(f"{PREFIX}_add"),
            "change": self.url("change"),
            "install": self.url("install_key"),
            "remove": self.url("remove_key"),
            "access check": self.url("run_access_check"),
        }

    def test_staff_without_the_core_app_get_403_everywhere(self):
        for apps in (["mail"], ["cms", "event"]):
            self.client.force_login(make_admin(apps=apps, email=f"staff-{'-'.join(apps)}@example.com"))
            for page, url in self.pages().items():
                with self.subTest(apps=apps, page=page):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(GmailApiSubject.objects.count(), 1)

    def test_core_staff_open_every_page_like_a_superuser(self):
        self.client.force_login(make_admin(apps=["core"], email="core-staff@example.com"))
        for page, url in self.pages().items():
            with self.subTest(page=page):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_core_staff_add_an_account_through_the_change_form(self):
        self.client.force_login(make_admin(apps=["core"], email="core-staff@example.com"))
        data = {
            "name": "Gmail",
            "credential_mail": "send",
            "max_recipients_per_message": 500,
            "max_message_bytes": 25_000_000,
            "subjects-TOTAL_FORMS": 2,
            "subjects-INITIAL_FORMS": 1,
            "subjects-0-id": self.config.subjects.get().pk,
            "subjects-0-config": self.config.pk,
            "subjects-0-subject": SUBJECT,
            "subjects-1-subject": "dean@g.ucmerced.edu",
        }
        response = self.client.post(self.url("change"), data)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.assertTrue(self.config.allows("dean@g.ucmerced.edu"))

    def test_a_superuser_sees_every_page(self):
        self.client.force_login(self.superuser)
        for url in (reverse(f"{PREFIX}_changelist"), self.url("change"), self.url("install_key")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_change_form_names_the_ceilings_in_force(self):
        self.client.force_login(self.superuser)
        overridden = {**settings.GMAIL_API, "max_recipients_per_message": 400, "max_message_bytes": 20_000_000}

        with override_settings(GMAIL_API=overridden):
            content = self.client.get(self.url("change")).content.decode()

        self.assertIn("At most 400 recipients (Google", content)
        self.assertIn("At most 20,000,000 bytes (Google", content)
        self.assertNotIn("Google allows 500", content)

    def test_the_superuser_adds_an_account_through_the_inline(self):
        self.client.force_login(self.superuser)
        data = {
            "name": "Gmail",
            "credential_mail": "send",
            "max_recipients_per_message": 500,
            "max_message_bytes": 25_000_000,
            "subjects-TOTAL_FORMS": 2,
            "subjects-INITIAL_FORMS": 1,
            "subjects-0-id": self.config.subjects.get().pk,
            "subjects-0-config": self.config.pk,
            "subjects-0-subject": SUBJECT,
            "subjects-1-subject": " Other@G.UCMerced.edu ",
        }
        response = self.client.post(self.url("change"), data)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.assertTrue(self.config.allows("other@g.ucmerced.edu"))

    def test_changelist_lookups_on_the_key_and_allow_list_are_refused(self):
        self.client.force_login(self.superuser)
        changelist = reverse(f"{PREFIX}_changelist")
        for lookup in ("key_secret_ref__regex", "key_version_id__startswith", "subjects__subject__regex", "key_id"):
            with self.subTest(lookup=lookup):
                self.assertEqual(self.client.get(changelist, {lookup: "^a"}).status_code, 400)
        self.assertEqual(self.client.get(changelist, {"is_active__exact": "1"}).status_code, 200)
