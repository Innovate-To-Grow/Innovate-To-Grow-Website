from unittest.mock import MagicMock, patch

from django.contrib.admin.options import IS_POPUP_VAR
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings

from apps.cms.models import CMSEmbedAllowedHost
from apps.core.admin.confirmation.pending import CACHE_FILE_PREFIX
from apps.core.tests.admin.confirm.test_confirm_on_save_direct import _asset_admin, _host_admin, _wire_request


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class FileUploadCachingTest(TestCase):
    """Covers caching uploaded files at confirm time and restoring on execute."""

    def tearDown(self):
        cache.clear()

    def test_add_with_file_caches_upload_and_restores_it(self):
        admin_obj = _asset_admin()
        factory = RequestFactory()

        upload = SimpleUploadedFile("doc.txt", b"hello-bytes", content_type="text/plain")
        request = _wire_request(
            factory.post(
                "/admin/",
                {"title": "My Asset", "asset_type": "image"},
            )
        )
        # Attach the uploaded file to the request.
        request.FILES["file"] = upload

        # Build a valid form result so changeform_view proceeds to caching.
        fake_form = MagicMock()
        fake_form.is_valid.return_value = True
        fake_form.cleaned_data = {"name": "My Asset"}

        with (
            patch.object(admin_obj, "get_form", return_value=lambda *a, **k: fake_form),
            patch(
                "apps.core.admin.confirmation.on_save.compute_add_diff",
                return_value=[{"field": "title", "label": "Title", "new_value": "My Asset"}],
            ),
            patch(
                "apps.core.admin.confirmation.pending.serialize_post_data",
                return_value={"title": ["My Asset"]},
            ),
        ):
            response = admin_obj.changeform_view(request, object_id=None)

        # Redirects to the confirm page, and the upload was cached.
        self.assertIsInstance(response, HttpResponseRedirect)
        session_key = admin_obj._session_key()
        pending = request.session[session_key]
        self.assertIn("file", pending["file_keys"])
        cache_key = pending["file_keys"]["file"]
        self.assertTrue(cache_key.startswith(CACHE_FILE_PREFIX))
        cached = cache.get(cache_key)
        self.assertEqual(cached["name"], "doc.txt")
        self.assertEqual(cached["content"], b"hello-bytes")

        # Now drive _do_confirmed_save and ensure the file is restored and cache cleared.
        confirm_request = _wire_request(factory.post("/admin/confirm/"))
        restored = {}

        def capture_super(req, object_id, form_url, extra):
            restored["file"] = req._files.get("file")
            return HttpResponseRedirect("/done/")

        with patch(
            "django.contrib.admin.options.ModelAdmin.changeform_view",
            side_effect=capture_super,
        ):
            admin_obj._do_confirmed_save(confirm_request, pending)

        self.assertIsNotNone(restored["file"])
        self.assertEqual(restored["file"].name, "doc.txt")
        self.assertEqual(restored["file"].read(), b"hello-bytes")
        # Cache entry consumed during restore.
        self.assertIsNone(cache.get(cache_key))

    def test_invalid_replacement_clears_old_pending_token_and_cached_files(self):
        admin_obj = _host_admin()
        factory = RequestFactory()
        first_request = _wire_request(
            factory.post(
                "/admin/",
                {"hostname": "first-valid.com", "is_active": "on"},
            )
        )
        first_request.FILES["attachment"] = SimpleUploadedFile(
            "first.txt",
            b"first-payload",
            content_type="text/plain",
        )

        first_response = admin_obj.changeform_view(first_request, object_id=None)

        self.assertIsInstance(first_response, HttpResponseRedirect)
        session_key = admin_obj._session_key()
        old_pending = first_request.session[session_key]
        old_token = old_pending["token"]
        old_cache_key = old_pending["file_keys"]["attachment"]
        self.assertIsNotNone(cache.get(old_cache_key))

        second_request = _wire_request(
            factory.post(
                "/admin/",
                {"hostname": "", "is_active": "on"},
            )
        )
        second_request.session = first_request.session
        normal_change_form = object()
        with patch(
            "django.contrib.admin.options.ModelAdmin.changeform_view",
            return_value=normal_change_form,
        ):
            second_response = admin_obj.changeform_view(second_request, object_id=None)

        self.assertIs(second_response, normal_change_form)
        self.assertNotIn(session_key, second_request.session)
        self.assertIsNone(cache.get(old_cache_key))
        self.assertNotEqual(second_request.session.get(session_key, {}).get("token"), old_token)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class DeleteViewBranchesTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = _host_admin()
        self.host = CMSEmbedAllowedHost.objects.create(hostname="del.com", is_active=True)

    def test_skip_confirmation_defers_to_super(self):
        request = _wire_request(self.factory.post("/admin/", {IS_POPUP_VAR: "1", "post": "yes"}))
        sentinel = object()
        with patch(
            "django.contrib.admin.options.ModelAdmin.delete_view",
            return_value=sentinel,
        ) as super_del:
            result = self.admin.delete_view(request, str(self.host.pk))
        self.assertIs(result, sentinel)
        super_del.assert_called_once()

    def test_confirmed_delete_marker_in_the_post_body_cannot_bypass_confirmation(self):
        request = _wire_request(self.factory.post("/admin/", {"_confirmed_delete": "1", "post": "yes"}))

        with patch("django.contrib.admin.options.ModelAdmin.delete_view") as super_view:
            response = self.admin.delete_view(request, str(self.host.pk))

        super_view.assert_not_called()
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertIn("confirm-change", response.url)

    def test_missing_object_defers_to_super(self):
        request = _wire_request(self.factory.post("/admin/", {"post": "yes"}))
        sentinel = object()
        with (
            patch.object(self.admin, "get_object", return_value=None),
            patch(
                "django.contrib.admin.options.ModelAdmin.delete_view",
                return_value=sentinel,
            ) as super_del,
        ):
            result = self.admin.delete_view(request, "deadbeef")
        self.assertIs(result, sentinel)
        super_del.assert_called_once()
