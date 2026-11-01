"""The Gmail API config admin: superusers only, the key pages (install, remove, access check), no echo of a submitted
key anywhere, and the changelist lookup guard."""

import json

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from apps.core.admin.service_credentials import gmail_api_forms
from apps.core.models import GmailApiProviderConfig, GmailApiSubject
from apps.core.services.email.gmail.key import parsing
from apps.core.tests.gmail_api_helpers import (
    KEY_ID,
    SERVICE_ACCOUNT,
    SUBJECT,
    FakePost,
    ec_pem,
    key_file,
    key_json,
    make_config,
    pem,
    reset_gmail_state,
    rsa_key,
    stored_config,
    token_error,
    token_response,
)
from apps.core.tests.services.gmail_api.test_gmail_access_check import ScopedTokenAnswers
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


class SuperuserOnlyTests(GmailAdminTestCase):
    def test_core_and_mail_staff_get_403_everywhere(self):
        staff = {
            "core": make_admin(apps=["core"], email="core-staff@example.com"),
            "mail": make_admin(apps=["mail"], email="mail-staff@example.com"),
        }
        pages = {
            "changelist": reverse(f"{PREFIX}_changelist"),
            "add": reverse(f"{PREFIX}_add"),
            "change": self.url("change"),
            "install": self.url("install_key"),
            "remove": self.url("remove_key"),
            "access check": self.url("run_access_check"),
        }
        for who, member in staff.items():
            self.client.force_login(member)
            for page, url in pages.items():
                with self.subTest(who=who, page=page):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertEqual(GmailApiSubject.objects.count(), 1)

    def test_core_staff_cannot_widen_the_allow_list_through_the_change_form(self):
        self.client.force_login(make_admin(apps=["core"], email="core-staff@example.com"))
        data = {
            "name": "Gmail",
            "credential_mail": "send",
            "max_recipients_per_message": 500,
            "max_message_bytes": 25_000_000,
            "subjects-TOTAL_FORMS": 1,
            "subjects-INITIAL_FORMS": 0,
            "subjects-0-subject": "dean@g.ucmerced.edu",
        }
        self.assertEqual(self.client.post(self.url("change"), data).status_code, 403)
        self.assertFalse(GmailApiSubject.objects.filter(subject="dean@g.ucmerced.edu").exists())

    def test_a_superuser_sees_every_page(self):
        self.client.force_login(self.superuser)
        for url in (reverse(f"{PREFIX}_changelist"), self.url("change"), self.url("install_key")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

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


class InstallKeyPageTests(GmailAdminTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def install(self, data, *answers):
        self.post = FakePost(*answers).install(self)
        return self.client.post(self.url("install_key"), data)

    def readable_after(self, response) -> list[str]:
        pages = [response.content.decode()]
        if response.status_code == 302:
            pages.append(self.client.get(response["Location"]).content.decode())
        history = [f"{entry.object_repr} {entry.change_message}" for entry in LogEntry.objects.all()]
        rows = [repr(list(GmailApiProviderConfig.objects.values())), str(self.client.cookies)]
        return [*pages, *history, *rows]

    def assert_no_echo(self, readable, submitted_pem):
        slices = pem_slices(submitted_pem)
        self.assertTrue(slices)
        for text in readable:
            self.assertNotIn("PRIVATE KEY-----", text)
            for piece in slices:
                self.assertNotIn(piece, text)

    def test_an_accepted_paste_installs_and_never_echoes(self):
        data = key_json()
        response = self.install({gmail_api_forms.KEY_FIELD: data}, token_response())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(tuple(response.wsgi_request.sensitive_post_parameters), (gmail_api_forms.KEY_FIELD,))
        self.config.refresh_from_db()
        self.assertEqual((self.config.key_id, self.config.service_account_email), (KEY_ID, SERVICE_ACCOUNT))
        self.assert_no_echo(self.readable_after(response), key_file()["private_key"])

    def test_an_accepted_upload_installs(self):
        upload = SimpleUploadedFile("key.json", key_json().encode(), content_type="application/json")
        response = self.install({gmail_api_forms.FILE_FIELD: upload}, token_response())
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertTrue(self.config.key_configured)

    def test_refused_submissions_render_no_part_of_the_key(self):
        other = pem(rsa_key(3072))
        cases = {
            "token_uri": (key_json(private_key=other, token_uri="https://evil.example/token"), parsing.BAD_TOKEN_URI),
            "small key": (key_json(private_key=pem(rsa_key(1024))), "smaller than the site accepts"),
            "ec key": (key_json(private_key=ec_pem()), "RSA keys"),
            "duplicate": (key_json(private_key=other)[:-1] + ', "type": "x"}', parsing.DUPLICATE_FIELD),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name):
                response = self.install({gmail_api_forms.KEY_FIELD: data})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, escape(message))
                submitted = json.loads(data)["private_key"]
                self.assert_no_echo(self.readable_after(response), submitted)
                self.assertEqual(self.post.calls, [])
        self.config.refresh_from_db()
        self.assertFalse(self.config.key_configured)

    def test_a_key_google_refuses_is_not_installed_and_not_echoed(self):
        data = key_json()
        response = self.install(
            {gmail_api_forms.KEY_FIELD: data}, token_error("invalid_grant", "Invalid JWT Signature.")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing was changed")
        self.assert_no_echo(self.readable_after(response), key_file()["private_key"])
        self.assertFalse(LogEntry.objects.exists())

    def test_text_and_file_together_and_an_oversized_upload_are_refused(self):
        upload = SimpleUploadedFile("key.json", key_json().encode())
        response = self.install({gmail_api_forms.KEY_FIELD: key_json(), gmail_api_forms.FILE_FIELD: upload})
        self.assertContains(response, gmail_api_forms.TEXT_AND_FILE)
        big = SimpleUploadedFile("key.json", b" " * 16_385)
        self.assertContains(self.install({gmail_api_forms.FILE_FIELD: big}), gmail_api_forms.FILE_TOO_LARGE)

    def test_a_blank_submit_keeps_the_installed_key(self):
        self.install({gmail_api_forms.KEY_FIELD: key_json()}, token_response())
        self.config.refresh_from_db()
        pinned = self.config.key_version_id
        response = self.install({gmail_api_forms.KEY_FIELD: ""})
        self.assertContains(response, gmail_api_forms.KEY_REQUIRED)
        self.config.refresh_from_db()
        self.assertEqual(self.config.key_version_id, pinned)


class RemoveAndCheckPageTests(GmailAdminTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def test_remove_key_unpins_and_records_the_reason(self):
        config = make_config()
        response = self.client.post(
            self.url("remove_key", config), {"confirmation": "REMOVE", "reason": "Rotating after a leak"}
        )
        self.assertEqual(response.status_code, 302)
        config.refresh_from_db()
        self.assertFalse(config.key_configured or config.is_active)
        self.assertIn("Rotating after a leak", LogEntry.objects.get().change_message)

    def test_remove_needs_the_confirmation_word(self):
        config = make_config()
        response = self.client.post(self.url("remove_key", config), {"confirmation": "yes", "reason": "x"})
        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertTrue(config.key_configured)

    def test_the_access_check_runs_only_on_post_and_shows_the_result(self):
        config = stored_config(checked=False, verified=False, subjects=(SUBJECT,), name="Checked")
        answers = ScopedTokenAnswers().install(self)
        self.assertEqual(self.client.get(self.url("run_access_check", config)).status_code, 200)
        self.assertEqual(answers.calls, [])
        response = self.client.post(self.url("run_access_check", config), {"send": "", "breadth": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "recorded as the access check evidence")
        config.refresh_from_db()
        self.assertTrue(config.access_check_current)
        self.assertEqual(self.client.put(self.url("run_access_check", config)).status_code, 405)
