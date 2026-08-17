"""Member admin saves with the confirm-on-save interstitial ENABLED.

Every other Member admin POST test sets ``ADMIN_REQUIRE_CONFIRMATION=False``, and
``config.settings.test`` defaults it off — but ``config.settings.local`` sets it True and production
falls through to ``getattr(settings, "ADMIN_REQUIRE_CONFIRMATION", True)``. So the flow real operators
use had no coverage, which is how two defects shipped:

* ``profile_image`` was always in ``form.changed_data`` (a TextField gets a plain CharField, whose
  ``has_changed`` coerces the widget's "no change" ``None`` to ``""``), so a no-op save still demanded
  a typed confirmation and the diff showed a base64 blob as both old and new value.
* ``Base64ImageWidget`` consumed the upload stream during validation, so the mixin cached zero bytes
  and the confirmed save wrote an empty ``data:`` URI over the member's real image.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.authn.tests.helpers import PNG_1PX_DATA_URI, png_upload, scrape_admin_form

Member = get_user_model()

SESSION_KEY = "_admin_pending_change_authn_member"


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=True)
class MemberConfirmOnSaveTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.superuser = Member.objects.create_superuser(
            password="super123", first_name="Super", last_name="User", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.superuser, email_address="super@example.com", email_type="primary", verified=True
        )
        self.target = Member.objects.create_user(
            password="target123",
            first_name="Target",
            last_name="User",
            is_active=True,
            profile_image=PNG_1PX_DATA_URI,
        )
        ContactEmail.objects.create(
            member=self.target, email_address="target@example.com", email_type="primary", verified=True
        )
        self.client.force_login(self.superuser)

    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def tearDown(self):
        cache.clear()

    def _change_url(self):
        return f"/admin/authn/member/{self.target.pk}/change/"

    def _post_data(self, overrides=None):
        return scrape_admin_form(self.client, self._change_url(), overrides)

    def _confirm_url(self):
        return reverse("admin:authn_member_confirm_change")

    # --- the phantom profile_image diff ---------------------------------------------------------

    def test_unchanged_save_skips_the_confirmation_page(self):
        response = self.client.post(self._change_url(), self._post_data())

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/confirm-change/", response["Location"])
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_diff_covers_only_the_edited_field(self):
        response = self.client.post(self._change_url(), self._post_data({"title": "Dean"}))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/confirm-change/", response["Location"])
        diff = self.client.session[SESSION_KEY]["diff"]
        self.assertEqual([row["field"] for row in diff], ["title"])

    def test_confirmation_page_never_embeds_a_base64_blob(self):
        self.client.post(self._change_url(), self._post_data({"title": "Dean"}))

        page = self.client.get(self._confirm_url())

        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "base64")
        self.assertNotContains(page, "Profile Image")

    def test_confirmed_save_persists_and_clears_the_session(self):
        self.client.post(self._change_url(), self._post_data({"title": "Dean"}))
        token = self.client.session[SESSION_KEY]["token"]

        response = self.client.post(self._confirm_url(), {"confirmation_word": "user", "token": token})

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.title, "Dean")
        self.assertNotIn(SESSION_KEY, self.client.session)

    # --- the destroyed avatar --------------------------------------------------------------------

    def test_uploaded_image_survives_the_confirm_round_trip(self):
        """The widget read the stream during validation, so the mixin cached b"" and the replayed
        save stored "data:image/png;base64," — destroying the previous image."""
        self.target.profile_image = "data:image/png;base64," + ("A" * 200)
        self.target.save(update_fields=["profile_image"])
        data = self._post_data()

        response = self.client.post(self._change_url(), data | {"profile_image": png_upload()})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/confirm-change/", response["Location"])

        pending = self.client.session[SESSION_KEY]
        cached = cache.get(pending["file_keys"]["profile_image"])
        self.assertTrue(cached["content"], "the upload was cached as zero bytes")

        confirmed = self.client.post(self._confirm_url(), {"confirmation_word": "user", "token": pending["token"]})

        self.assertEqual(confirmed.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.profile_image, PNG_1PX_DATA_URI)

    def test_expired_upload_is_reported_instead_of_saving_without_the_file(self):
        """The payload lives in a per-container cache in production; a miss must not save silently."""
        self.target.profile_image = ""
        self.target.save(update_fields=["profile_image"])
        data = self._post_data()
        self.client.post(self._change_url(), data | {"profile_image": png_upload()})
        pending = self.client.session[SESSION_KEY]
        cache.delete(pending["file_keys"]["profile_image"])

        response = self.client.post(self._confirm_url(), {"confirmation_word": "user", "token": pending["token"]})

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.profile_image, "")
        self.assertNotIn(SESSION_KEY, self.client.session)

    # --- autosave -------------------------------------------------------------------------------

    def test_autosave_post_actually_saves(self):
        """The shipped autosave client sends _autosave so it bypasses the interstitial."""
        data = self._post_data({"title": "Autosaved"})
        data.pop("_save", None)
        data["_continue"] = "1"
        data["_autosave"] = "1"

        response = self.client.post(self._change_url(), data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.target.refresh_from_db()
        self.assertEqual(self.target.title, "Autosaved")
        self.assertNotIn("/confirm-change/", response.get("Location", ""))
        self.assertNotIn(SESSION_KEY, self.client.session)
