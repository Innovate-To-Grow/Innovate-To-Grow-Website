from apps.authn.tests.admin.actions.test_admin_actions import _MemberAdminActionCase, _request


class MemberAdminActionTests(_MemberAdminActionCase):
    def test_profile_image_view_serves_the_decoded_bytes(self):
        from apps.authn.tests.helpers import PNG_1PX, PNG_1PX_DATA_URI

        self.m1.profile_image = PNG_1PX_DATA_URI
        self.m1.save(update_fields=["profile_image"])
        request = _request(self.rf, self.admin_user)

        response = self.model_admin.profile_image_view(request, str(self.m1.pk))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response.content, PNG_1PX)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_profile_image_view_404s_without_an_image(self):
        from django.http import Http404

        request = _request(self.rf, self.admin_user)
        with self.assertRaises(Http404):
            self.model_admin.profile_image_view(request, str(self.m1.pk))

    def test_profile_image_view_forces_download_for_a_non_image_type(self):
        """Legacy rows could hold any client-supplied type; never render one inline."""
        import base64

        self.m1.profile_image = "data:text/html;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
        self.m1.save(update_fields=["profile_image"])
        request = _request(self.rf, self.admin_user)

        response = self.model_admin.profile_image_view(request, str(self.m1.pk))

        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_export_excel_view(self):
        request = _request(self.rf, self.admin_user)
        response = self.model_admin.export_excel_view(request)
        self.assertEqual(response.status_code, 200)
